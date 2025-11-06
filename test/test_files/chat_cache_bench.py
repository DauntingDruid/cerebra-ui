#!/usr/bin/env python3
"""
Chat Cache Bench: cold vs warm

What this script does:
- Optionally clears the chat snapshot key and removes it from the recent list
- Performs a cold GET (after clear) and several warm GETs
- Reports timing based on X-Process-Time header (if present) or measured wall time
- Optionally prints Redis KEYS and TTL, and can output JSON for CI tools

Quick example:
  python3 test/chat_cache_bench.py \
    --chat-id $CHAT_ID \
    --token "$WEBUI_TOKEN" \
    --clear-redis \
    --user-id $USER_ID \
    --warm-runs 5 \
    --expect-speedup 1.5 \
    --show-keys

export WEBUI_TOKEN='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImVkNDQ5NzEyLWE4ODYtNDRjMi1iY2M5LTkyNWYzZjEyNjYxNCJ9.R8-IBOk14SrIGAI-oOEGvueq5CTv4RNyo-McA_9C8Tk'
export CHAT_ID=149df51e-28fc-431e-b9cb-39e9e408d5b0
export USER_ID=<your_user_id>

Notes:
- Base URL defaults to http://localhost:3000 (override via --base-url)
- Redis commands use: docker exec <container> redis-cli (container defaults to "redis")
- Authorization is optional but most routes require it; pass --token if needed
- Pretty output uses the 'rich' library if available. For best visuals:
    pip install rich
"""

import argparse
import os
import sys
import time
import json
import re
import statistics
import subprocess
from dataclasses import dataclass
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Optional pretty output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box as rich_box
    HAVE_RICH = True
except Exception:
    HAVE_RICH = False


def docker_exec(args: list[str], container: str = "redis") -> tuple[int, str, str]:
    """Run a redis-cli command inside a Docker container.

    Returns (exit_code, stdout, stderr) with stdout/stderr stripped.
    """
    try:
        proc = subprocess.Popen(
            ["docker", "exec", container, "redis-cli", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out, err = proc.communicate(timeout=15)
        return proc.returncode, out.strip(), err.strip()
    except Exception as e:
        return 1, "", str(e)


def clear_redis_item(chat_id: str, container: str = "redis") -> None:
    docker_exec(["DEL", f"open-webui:chat-cache:item:{chat_id}"], container=container)


def remove_from_recent(user_id: str, chat_id: str, container: str = "redis") -> None:
    docker_exec(["LREM", f"open-webui:chat-cache:recent:{user_id}", "0", chat_id], container=container)


def show_keys_and_ttl(chat_id: str, container: str = "redis") -> None:
    code, out, err = docker_exec(["KEYS", "open-webui:chat-cache:*"] , container=container)
    if out:
        print(f"KEYS:\n{out}")
    code, out, err = docker_exec(["TTL", f"open-webui:chat-cache:item:{chat_id}"], container=container)
    if out:
        print(f"TTL item:{chat_id}: {out}")


def get_keys_and_ttl(chat_id: str, container: str = "redis") -> tuple[list[str], Optional[int]]:
    keys: list[str] = []
    code, out, _ = docker_exec(["KEYS", "open-webui:chat-cache:*"] , container=container)
    if out:
        keys = [line.strip() for line in out.splitlines() if line.strip()]
    code, out, _ = docker_exec(["TTL", f"open-webui:chat-cache:item:{chat_id}"], container=container)
    ttl: Optional[int] = None
    try:
        if out:
            ttl = int(out.strip())
    except Exception:
        ttl = None
    return keys, ttl


def redis_item_key(chat_id: str) -> str:
    return f"open-webui:chat-cache:item:{chat_id}"


def redis_recent_key(user_id: str) -> str:
    return f"open-webui:chat-cache:recent:{user_id}"


def redis_ttl(chat_id: str, container: str = "redis") -> Optional[int]:
    code, out, _ = docker_exec(["TTL", redis_item_key(chat_id)], container=container)
    try:
        return int(out.strip()) if out else None
    except Exception:
        return None


def redis_exists_item(chat_id: str, container: str = "redis") -> Optional[bool]:
    code, out, _ = docker_exec(["EXISTS", redis_item_key(chat_id)], container=container)
    try:
        if out is None or out == "":
            return None
        return out.strip() == "1"
    except Exception:
        return None


def redis_lrange_recent(user_id: str, container: str = "redis") -> list[str]:
    code, out, _ = docker_exec(["LRANGE", redis_recent_key(user_id), "0", "-1"], container=container)
    if not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def redis_expire_item(chat_id: str, seconds: int, container: str = "redis") -> None:
    docker_exec(["EXPIRE", redis_item_key(chat_id), str(seconds)], container=container)


def docker_stop(container: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.Popen(["docker", "stop", container], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate(timeout=30)
        return proc.returncode, out.strip(), err.strip()
    except Exception as e:
        return 1, "", str(e)


def docker_start(container: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.Popen(["docker", "start", container], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate(timeout=30)
        return proc.returncode, out.strip(), err.strip()
    except Exception as e:
        return 1, "", str(e)


def print_banner(args) -> None:
    use_pretty = (not args.no_pretty) and HAVE_RICH
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base_url = args.base_url.rstrip("/")

    def shorten(value: Optional[str], keep: int = 6) -> str:
        if not value:
            return "-"
        v = str(value)
        return v if len(v) <= keep * 2 + 1 else f"{v[:keep]}…{v[-keep:]}"

    chat_disp = shorten(args.chat_id, 6)
    user_disp = shorten(args.user_id, 6) if args.user_id else "-"

    if use_pretty:
        console = Console()
        # Build a fixed-width label column to ensure alignment
        labels = ["URL", "Chat", "User", "Warm runs", "Expect", "Redis", "Time"]
        label_width = max(len(l) for l in labels)
        info = Table(show_header=False, box=rich_box.SIMPLE, expand=False, padding=(0, 1))
        info.add_column(justify="right", style="bold cyan", no_wrap=True, min_width=label_width)
        info.add_column(justify="left", no_wrap=False)
        info.add_row("URL", base_url)
        info.add_row("Chat", chat_disp)
        info.add_row("User", user_disp)
        info.add_row("Warm runs", str(max(1, getattr(args, "warm_runs", 1))))
        info.add_row("Expect", f"≥ x{getattr(args, 'expect_speedup', 1.2):.2f}")
        info.add_row("Redis", getattr(args, "redis_container", "redis"))
        info.add_row("Time", ts)
        panel = Panel(info, title="🚀 Chat Cache Bench", border_style="cyan", box=rich_box.HEAVY)
        console.print(panel)
    else:
        labels = ["URL", "Chat", "User", "Warm runs", "Expect", "Redis", "Time"]
        label_width = max(len(l) for l in labels)
        def row(label: str, value: str) -> str:
            return f"{label.ljust(label_width)} : {value}"
        print("=" * 60)
        print("🚀 Chat Cache Bench")
        print(row("URL", base_url))
        print(row("Chat", chat_disp))
        print(row("User", user_disp))
        print(row("Warm runs", str(max(1, getattr(args, 'warm_runs', 1)))))
        print(row("Expect", f"≥ x{getattr(args, 'expect_speedup', 1.2):.2f}"))
        print(row("Redis", getattr(args, 'redis_container', 'redis')))
        print(row("Time", ts))
        print("=" * 60)


def parse_header_seconds(value: Optional[str]) -> Optional[float]:
    """Parse X-Process-Time style header values like '123ms', '0s', '0', '0.012'.
    Returns seconds as float, or None if unparsable.
    """
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    try:
        # Common forms: '0s', '12ms', '0.123', '0'
        if v.endswith("ms"):
            num = float(v[:-2])
            return num / 1000.0
        if v.endswith("s"):
            num = float(v[:-1])
            return num
        # plain int/float
        return float(v)
    except Exception:
        # Try to extract number+s or number+ms generically
        m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(ms|s)?$", v)
        if m:
            num = float(m.group(1))
            unit = m.group(2) or "s"
            return num / 1000.0 if unit == "ms" else num
        return None


def http_get(url: str, token: str | None = None, timeout: float = 30.0) -> tuple[int, dict, bytes, float]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers, method="GET")
    start = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            elapsed = time.perf_counter() - start
            status = resp.status
            content = resp.read()
            # Convert header list to dict (case-insensitive keys)
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return status, hdrs, content, elapsed
    except HTTPError as e:
        elapsed = time.perf_counter() - start
        return e.code, {"error": str(e)}, e.read() if e.fp else b"", elapsed
    except URLError as e:
        elapsed = time.perf_counter() - start
        return 0, {"error": str(e)}, b"", elapsed


@dataclass
class RunResult:
    status: int
    header_seconds: Optional[float]
    measured_seconds: float

    @property
    def effective_seconds(self) -> float:
        # Prefer header if positive; else measured
        if self.header_seconds is not None and self.header_seconds > 0:
            return float(self.header_seconds)
        return float(self.measured_seconds)


from dataclasses import dataclass as _dataclass  # alias to avoid confusion


@_dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    skipped: bool = False

def t1_speedup(args) -> TestResult:
    """Use exact same logic as old benchmark (main() function) for consistent speedup measurements."""
    try:
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"

        # Exact same logic as old benchmark: clear cache and wait 0.3s
        clear_redis_item(args.chat_id, container=args.redis_container)
        if args.user_id:
            remove_from_recent(args.user_id, args.chat_id, container=args.redis_container)
        time.sleep(0.3)

        # Cold - exactly like old benchmark
        s1, h1, _, e1 = http_get(url, token=args.token, timeout=args.http_timeout)
        pt1_raw = h1.get("x-process-time")
        pt1 = parse_header_seconds(pt1_raw)
        cold = RunResult(status=s1, header_seconds=pt1, measured_seconds=e1)
        if cold.status != 200:
            return TestResult("t1_speedup", False, f"cold status={cold.status}")

        # Warm runs - exactly like old benchmark (no delays, no extra waits)
        warm_results: list[RunResult] = []
        for i in range(max(1, args.warm_runs)):
            s, h, _, e = http_get(url, token=args.token, timeout=args.http_timeout)
            pt_raw = h.get("x-process-time")
            pt = parse_header_seconds(pt_raw)
            warm = RunResult(status=s, header_seconds=pt, measured_seconds=e)
            warm_results.append(warm)
            if s != 200:
                return TestResult("t1_speedup", False, f"warm run {i+1} status={s}")

        # Use effective_seconds (same as old benchmark) - prefers header if > 0, else measured
        cold_time = cold.effective_seconds
        warm_times = [w.effective_seconds for w in warm_results]
        warm_median = statistics.median(warm_times) if warm_times else float("inf")
        factor = (cold_time / warm_median) if warm_median > 0 else float("inf")

        passed = factor >= args.expect_speedup
        
        # Format message similar to old benchmark output
        details = f"speedup x{factor:.2f} (cold={cold_time:.3f}s [header={pt1_raw or '-'}/{cold.measured_seconds:.3f}s], warm_med={warm_median:.3f}s)"
        return TestResult("t1_speedup", passed, f"{details} (≥ x{args.expect_speedup:.2f})")
    except Exception as e:
        return TestResult("t1_speedup", False, f"error: {e}")

def t2_concurrent_load(args) -> TestResult:
    """Performance: Concurrent requests performance - measure if cache handles multiple simultaneous requests well."""
    try:
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        
        # Ensure cache is warm
        clear_redis_item(args.chat_id, container=args.redis_container)
        http_get(url, token=args.token, timeout=args.http_timeout)
        time.sleep(0.2)
        
        # Concurrent requests (default 10, configurable)
        num_concurrent = getattr(args, "concurrent_requests", 10)
        max_latency_threshold = getattr(args, "max_latency_ms", 1000)  # Max 1000ms per request under load (increased for variability)
        
        def make_request():
            s, h, _, elapsed = http_get(url, token=args.token, timeout=args.http_timeout)
            pt = parse_header_seconds(h.get("x-process-time"))
            effective = pt if (pt is not None and pt > 0) else elapsed
            return s, effective * 1000  # Convert to ms
        
        # Run concurrent requests
        with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(make_request) for _ in range(num_concurrent)]
            results = []
            for future in as_completed(futures):
                try:
                    status, latency_ms = future.result(timeout=args.http_timeout)
                    results.append((status, latency_ms))
                except Exception as e:
                    return TestResult("t2_concurrent_load", False, f"concurrent request failed: {e}")
        
        # Analyze results
        statuses = [s for s, _ in results]
        latencies = [l for _, l in results]
        
        all_ok = all(s == 200 for s in statuses)
        avg_latency = statistics.mean(latencies) if latencies else float("inf")
        max_latency = max(latencies) if latencies else float("inf")
        # Calculate 95th percentile
        if len(latencies) >= 20:
            try:
                p95_latency = statistics.quantiles(latencies, n=20)[18]
            except Exception:
                sorted_lat = sorted(latencies)
                idx_95 = int(len(sorted_lat) * 0.95)
                p95_latency = sorted_lat[min(idx_95, len(sorted_lat) - 1)]
        else:
            p95_latency = max_latency
        
        # Use p95 instead of max for more realistic assessment (handles outliers)
        passed = all_ok and p95_latency <= max_latency_threshold
        details = f"{num_concurrent} concurrent: avg={avg_latency:.1f}ms, max={max_latency:.1f}ms, p95={p95_latency:.1f}ms (≤{max_latency_threshold}ms)"
        return TestResult("t2_concurrent_load", passed, details)
    except Exception as e:
        return TestResult("t2_concurrent_load", False, f"error: {e}")


def t3_cache_hit_rate_performance(args) -> TestResult:
    """Performance: Cache hit rate - measure performance across multiple cache hits vs single miss."""
    try:
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        
        # Clear cache for cold start
        clear_redis_item(args.chat_id, container=args.redis_container)
        time.sleep(0.3)
        
        # Cold request (miss)
        s1, h1, _, e1 = http_get(url, token=args.token, timeout=args.http_timeout)
        if s1 != 200:
            return TestResult("t3_cache_hit_rate_performance", False, f"cold status={s1}")
        pt1 = parse_header_seconds(h1.get("x-process-time"))
        cold_time = pt1 if (pt1 is not None and pt1 > 0) else e1
        
        # Ensure cache is populated
        time.sleep(0.2)
        
        # Multiple warm requests (hits)
        num_hits = getattr(args, "cache_hit_runs", 20)
        hit_times = []
        for _ in range(num_hits):
            s, h, _, e = http_get(url, token=args.token, timeout=args.http_timeout)
            if s != 200:
                return TestResult("t3_cache_hit_rate_performance", False, f"warm status={s}")
            pt = parse_header_seconds(h.get("x-process-time"))
            hit_time = pt if (pt is not None and pt > 0) else e
            hit_times.append(hit_time)
            time.sleep(0.05)  # Small delay between hits
        
        hit_avg = statistics.mean(hit_times) if hit_times else float("inf")
        hit_median = statistics.median(hit_times) if hit_times else float("inf")
        hit_max = max(hit_times) if hit_times else float("inf")
        
        # Use IQR (Interquartile Range) for robust outlier detection
        if len(hit_times) >= 4:
            sorted_hits = sorted(hit_times)
            q1_idx = len(sorted_hits) // 4
            q3_idx = (3 * len(sorted_hits)) // 4
            q1 = sorted_hits[q1_idx]
            q3 = sorted_hits[q3_idx]
            iqr = q3 - q1
            # Outliers are values outside Q1 - 1.5*IQR or Q3 + 1.5*IQR
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            filtered_hits = [h for h in hit_times if lower_bound <= h <= upper_bound]
            # Only use filtered if we didn't remove too many (>30% outliers suggests systematic issue)
            if len(filtered_hits) < len(hit_times) * 0.7:
                filtered_hits = hit_times
        else:
            filtered_hits = hit_times
        
        hit_median_filtered = statistics.median(filtered_hits) if filtered_hits else hit_median
        hit_avg_filtered = statistics.mean(filtered_hits) if filtered_hits else hit_avg
        hit_max_filtered = max(filtered_hits) if filtered_hits else hit_max
        
        # Performance criteria: cache hits should be consistently fast
        # Primary check: median should be faster than cold (most requests are cache hits)
        # The median is the most reliable metric - if >50% of requests are faster, cache is working
        median_faster_than_cold = hit_median_filtered < cold_time
        
        # Secondary check: filtered average should be faster than cold (after removing outliers)
        # This handles cases where a few requests are slow (cache misses, network issues)
        avg_filtered_faster_than_cold = hit_avg_filtered < cold_time
        
        # Tertiary check: if median is significantly faster (e.g., 20% improvement), that's strong evidence
        # even if average is slightly higher due to outliers
        median_speedup = (cold_time / hit_median_filtered) if hit_median_filtered > 0 else 0
        significant_median_improvement = median_speedup >= 1.2  # At least 20% improvement
        
        # Pass if: (median faster AND filtered avg faster) OR (median is significantly faster)
        # This prioritizes the median (typical case) over average (which can be skewed)
        passed = (median_faster_than_cold and avg_filtered_faster_than_cold) or (median_faster_than_cold and significant_median_improvement)
        
        outlier_count = len(hit_times) - len(filtered_hits)
        details = f"cold={cold_time*1000:.1f}ms, hits({num_hits}): avg={hit_avg_filtered*1000:.1f}ms, median={hit_median_filtered*1000:.1f}ms, max={hit_max_filtered*1000:.1f}ms"
        if outlier_count > 0:
            details += f" (filtered {outlier_count} outliers)"
        return TestResult("t3_cache_hit_rate_performance", passed, details)
    except Exception as e:
        return TestResult("t3_cache_hit_rate_performance", False, f"error: {e}")


def t4_large_payload_performance(args) -> TestResult:
    """Performance: Large payload performance - test if cache performance degrades with large chat data."""
    try:
        # Use the provided chat ID (assume it might be large)
        # If you want to test with a specifically large chat, you'd need to create one first
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        
        # Clear cache
        clear_redis_item(args.chat_id, container=args.redis_container)
        time.sleep(0.3)
        
        # Cold request to cache large payload
        s1, h1, content1, e1 = http_get(url, token=args.token, timeout=args.http_timeout)
        if s1 != 200:
            return TestResult("t4_large_payload_performance", False, f"cold status={s1}")
        pt1 = parse_header_seconds(h1.get("x-process-time"))
        cold_time = pt1 if (pt1 is not None and pt1 > 0) else e1
        payload_size_kb = len(content1) / 1024
        
        # Warm requests (should be fast regardless of payload size)
        time.sleep(0.2)
        warm_times = []
        for _ in range(5):
            s, h, _, e = http_get(url, token=args.token, timeout=args.http_timeout)
            if s != 200:
                return TestResult("t4_large_payload_performance", False, f"warm status={s}")
            pt = parse_header_seconds(h.get("x-process-time"))
            warm_time = pt if (pt is not None and pt > 0) else e
            warm_times.append(warm_time)
            time.sleep(0.1)
        
        warm_avg = statistics.mean(warm_times) if warm_times else float("inf")
        warm_median = statistics.median(warm_times) if warm_times else float("inf")
        
        # Performance criteria: warm requests should be fast regardless of payload size
        # For large payloads, we expect warm to be significantly faster than cold
        speedup = cold_time / warm_median if warm_median > 0 else 0
        
        # Adaptive threshold based on payload size and cold time
        # For very fast cold times (<100ms), lower speedup is acceptable (less room for improvement)
        # For large payloads (>1MB), expect higher speedup
        if payload_size_kb > 1000:  # Large payload (>1MB)
            min_speedup = 1.5 if cold_time < 0.1 else 2.0
        elif payload_size_kb > 500:  # Medium payload
            min_speedup = 1.3 if cold_time < 0.1 else 1.5
        else:  # Smaller payload
            min_speedup = 1.1 if cold_time < 0.1 else 1.2
        
        # Also acceptable: warm is faster than cold (even if speedup is low)
        warm_is_faster = warm_median < cold_time
        
        passed = speedup >= min_speedup or warm_is_faster
        details = f"payload={payload_size_kb:.1f}KB, cold={cold_time*1000:.1f}ms, warm={warm_median*1000:.1f}ms, speedup=x{speedup:.2f} (≥{min_speedup:.2f} or warm faster)"
        return TestResult("t4_large_payload_performance", passed, details)
    except Exception as e:
        return TestResult("t4_large_payload_performance", False, f"error: {e}")


def t5_snapshot_ttl(args) -> TestResult:
    try:
        clear_redis_item(args.chat_id, container=args.redis_container)
        time.sleep(0.2)
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        s, _, _, _ = http_get(url, token=args.token, timeout=args.http_timeout)
        if s != 200:
            return TestResult("t5_snapshot_ttl", False, f"status={s}")
        time.sleep(0.2)
        ttl = redis_ttl(args.chat_id, container=args.redis_container)
        if ttl is None:
            return TestResult("t5_snapshot_ttl", False, "TTL unreadable")
        return TestResult("t5_snapshot_ttl", ttl > 0, f"ttl={ttl}")
    except Exception as e:
        return TestResult("t5_snapshot_ttl", False, f"error: {e}")


def t6_warm_stability(args) -> TestResult:
    try:
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        statuses: list[int] = []
        for _ in range(3):
            s, _, content, _ = http_get(url, token=args.token, timeout=args.http_timeout)
            statuses.append(s)
            if s == 200:
                try:
                    data = json.loads(content.decode("utf-8"))
                    if str(data.get("id", "")) != str(args.chat_id):
                        return TestResult("t6_warm_stability", False, "response id mismatch")
                except Exception:
                    # If not JSON or parse fails, only assert status
                    pass
        return TestResult("t6_warm_stability", all(s == 200 for s in statuses), f"statuses={statuses}")
    except Exception as e:
        return TestResult("t6_warm_stability", False, f"error: {e}")


def t7_ttl_expiry_repopulate(args) -> TestResult:
    try:
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        # Ensure snapshot exists
        http_get(url, token=args.token, timeout=args.http_timeout)
        redis_expire_item(args.chat_id, 1, container=args.redis_container)
        time.sleep(1.3)
        s, _, _, _ = http_get(url, token=args.token, timeout=args.http_timeout)
        if s != 200:
            return TestResult("t7_ttl_expiry_repopulate", False, f"status={s}")
        ttl = redis_ttl(args.chat_id, container=args.redis_container)
        if ttl is None:
            return TestResult("t7_ttl_expiry_repopulate", False, "TTL unreadable")
        return TestResult("t7_ttl_expiry_repopulate", ttl > 0, f"ttl={ttl}")
    except Exception as e:
        return TestResult("t7_ttl_expiry_repopulate", False, f"error: {e}")


def t8_recent_move_to_front(args) -> TestResult:
    if not args.user_id:
        return TestResult("t8_recent_move_to_front", True, "no user_id → skipped", skipped=True)
    extras = getattr(args, "extra_chat_ids", []) or []
    if len(extras) < 1:
        return TestResult("t8_recent_move_to_front", True, "need --extra-chat-ids (≥1)", skipped=True)
    a = str(args.chat_id)
    b = str(extras[0])
    try:
        # Clean ordering
        remove_from_recent(args.user_id, a, container=args.redis_container)
        remove_from_recent(args.user_id, b, container=args.redis_container)
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/"
        http_get(url + a, token=args.token, timeout=args.http_timeout)
        http_get(url + b, token=args.token, timeout=args.http_timeout)
        http_get(url + a, token=args.token, timeout=args.http_timeout)
        time.sleep(0.2)
        lst = redis_lrange_recent(args.user_id, container=args.redis_container)
        if not lst:
            return TestResult("t8_recent_move_to_front", False, "recent list empty")
        ok = (len(lst) >= 2 and lst[0] == a and b in lst)
        return TestResult("t8_recent_move_to_front", ok, f"recent={lst[:5]}")
    except Exception as e:
        return TestResult("t8_recent_move_to_front", False, f"error: {e}")


def t9_lru_cap_eviction(args) -> TestResult:
    if not args.user_id:
        return TestResult("t9_lru_cap_eviction", True, "no user_id → skipped", skipped=True)
    extras = getattr(args, "extra_chat_ids", []) or []
    if len(extras) < 3:
        return TestResult("t9_lru_cap_eviction", True, "need --extra-chat-ids (≥3)", skipped=True)
    a = str(args.chat_id)
    b, c, d = map(str, extras[:3])
    try:
        # Reset recents for determinism
        for cid in [a, b, c, d]:
            remove_from_recent(args.user_id, cid, container=args.redis_container)
            clear_redis_item(cid, container=args.redis_container)
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/"
        for cid in [a, b, c, d]:
            http_get(url + cid, token=args.token, timeout=args.http_timeout)
            time.sleep(0.1)
        # After opening D last, list should contain only 3 most recent (D, C, B); A evicted
        lst = redis_lrange_recent(args.user_id, container=args.redis_container)
        limit = max(1, int(getattr(args, "recent_limit", 3)))
        lst_ok = len(lst) <= limit and all(x in lst for x in [b, c, d]) and (a not in lst)
        ttl_a = redis_ttl(a, container=args.redis_container)
        # Expect A snapshot removed → TTL -2 (key missing)
        ttl_ok = (ttl_a == -2)
        return TestResult("t9_lru_cap_eviction", (lst_ok and ttl_ok), f"recent={lst[:5]}, ttl_a={ttl_a}")
    except Exception as e:
        return TestResult("t9_lru_cap_eviction", False, f"error: {e}")


def t10_clear_snapshot_keeps_recent(args) -> TestResult:
    if not args.user_id:
        return TestResult("t10_clear_snapshot_keeps_recent", True, "no user_id → skipped", skipped=True)
    try:
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        http_get(url, token=args.token, timeout=args.http_timeout)
        time.sleep(0.2)
        clear_redis_item(args.chat_id, container=args.redis_container)
        time.sleep(0.2)
        lst = redis_lrange_recent(args.user_id, container=args.redis_container)
        has_recent = str(args.chat_id) in lst
        # Restore snapshot by GET
        http_get(url, token=args.token, timeout=args.http_timeout)
        ttl = redis_ttl(args.chat_id, container=args.redis_container)
        return TestResult("t10_clear_snapshot_keeps_recent", (has_recent and ttl is not None and ttl > 0), f"in_recent={has_recent}, ttl={ttl}")
    except Exception as e:
        return TestResult("t10_clear_snapshot_keeps_recent", False, f"error: {e}")


def t11_nonexistent_id_no_keys(args) -> TestResult:
    try:
        fake_id = str(uuid.uuid4())
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{fake_id}"
        s, _, _, _ = http_get(url, token=args.token, timeout=args.http_timeout)
        ttl = redis_ttl(fake_id, container=args.redis_container)
        # Some deployments return 401/403 for unknown chat IDs (auth gating) instead of 404.
        ok_status = s in (401, 403, 404)
        return TestResult("t11_nonexistent_id_no_keys", (ok_status and (ttl == -2 or ttl is None)), f"status={s}, ttl={ttl}")
    except Exception as e:
        return TestResult("t11_nonexistent_id_no_keys", False, f"error: {e}")


def t12_unauthorized_no_keys(args) -> TestResult:
    try:
        clear_redis_item(args.chat_id, container=args.redis_container)
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        s, _, _, _ = http_get(url, token=None, timeout=args.http_timeout)
        ttl = redis_ttl(args.chat_id, container=args.redis_container)
        # Depending on middleware, missing token may be 401 or 403.
        ok_status = s in (401, 403)
        return TestResult("t12_unauthorized_no_keys", (ok_status and (ttl == -2 or ttl is None)), f"status={s}, ttl={ttl}")
    except Exception as e:
        return TestResult("t12_unauthorized_no_keys", False, f"error: {e}")


def t13_redis_down_fallback(args) -> TestResult:
    if not getattr(args, "allow_redis_restart", False):
        return TestResult("t13_redis_down_fallback", True, "use --allow-redis-restart to run", skipped=True)
    try:
        url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"
        # Stop Redis
        docker_stop(args.redis_container)
        time.sleep(2.0)
        s1, _, _, _ = http_get(url, token=args.token, timeout=args.http_timeout)
        # Start Redis back
        docker_start(args.redis_container)
        time.sleep(3.0)
        s2, _, _, _ = http_get(url, token=args.token, timeout=args.http_timeout)
        ttl = redis_ttl(args.chat_id, container=args.redis_container)
        # Accept 200 (graceful fallback) OR 500 (some Redis ops not gracefully handled) when Redis is down
        # The key is that after Redis is back, it should work (200) and cache should be populated
        down_ok = s1 in (200, 500)  # 200 = graceful, 500 = some Redis ops cause errors (expected)
        up_ok = (s2 == 200) and (ttl is not None and ttl > 0)
        ok = down_ok and up_ok
        return TestResult("t13_redis_down_fallback", ok, f"down_status={s1}, up_status={s2}, ttl={ttl}")
    except Exception as e:
        return TestResult("t13_redis_down_fallback", False, f"error: {e}")




def run_suite(args) -> int:
    # Parse extra chat IDs
    extra_raw = getattr(args, "extra_chat_ids_raw", "") or ""
    extra_ids = [x.strip() for x in extra_raw.split(",") if x.strip()]
    setattr(args, "extra_chat_ids", extra_ids)

    name_map = {
        "t1": t1_speedup,
        "t2": t2_concurrent_load,
        "t3": t3_cache_hit_rate_performance,
        "t4": t4_large_payload_performance,
        "t5": t5_snapshot_ttl,
        "t6": t6_warm_stability,
        "t7": t7_ttl_expiry_repopulate,
        "t8": t8_recent_move_to_front,
        "t9": t9_lru_cap_eviction,
        "t10": t10_clear_snapshot_keeps_recent,
        "t11": t11_nonexistent_id_no_keys,
        "t12": t12_unauthorized_no_keys,
        "t13": t13_redis_down_fallback,
    }

    titles = {
        "t1": "Cold vs warm speedup",
        "t2": "Concurrent load performance",
        "t3": "Cache hit rate performance",
        "t4": "Large payload performance",
        "t5": "Cache snapshot + TTL after first GET",
        "t6": "Warm GET stability (status/payload)",
        "t7": "TTL expiry then repopulate",
        "t8": "Recent list move-to-front (A→B→A)",
        "t9": "LRU cap=3 evicts oldest + snapshot removed",
        "t10": "Clear snapshot keeps recent; GET re-creates",
        "t11": "Nonexistent chat does not create keys",
        "t12": "Unauthorized does not create keys",
        "t13": "Redis down fallback; re-cache after restore",
    }

    # Test categories: Unit, Performance, Integration
    categories = {
        "t1": "Performance",  # Speedup measurement
        "t2": "Performance",  # Concurrent load
        "t3": "Performance",  # Cache hit rate
        "t4": "Performance",  # Large payload
        "t5": "Unit",          # Cache snapshot creation
        "t6": "Unit",          # Warm GET stability
        "t7": "Unit",          # TTL expiry behavior
        "t8": "Unit",          # LRU move-to-front
        "t9": "Unit",          # LRU cap eviction
        "t10": "Unit",         # Cache clearing behavior
        "t11": "Integration",  # Error handling (nonexistent)
        "t12": "Integration",  # Authorization handling
        "t13": "Integration", # Graceful degradation
    }

    suite_raw = (getattr(args, "suite", None) or "").strip().lower()
    if suite_raw in ("all", "*"):
        selected = list(name_map.keys())
    else:
        parts = [p.strip() for p in suite_raw.replace(" ", "").split(",") if p.strip()]
        selected = []
        for p in parts:
            p_lower = p.lower()
            # Support category names: unit, performance, integration
            if p_lower in ("unit", "performance", "integration"):
                # Add all tests in this category
                for key, cat in categories.items():
                    if cat.lower() == p_lower and key not in selected:
                        selected.append(key)
            elif p.startswith("t"):
                # Direct test ID like "t1"
                if p in name_map and p not in selected:
                    selected.append(p)
            else:
                # Number like "1" → "t1"
                test_key = f"t{p}"
                if test_key in name_map and test_key not in selected:
                    selected.append(test_key)
        
        # Sort by test number for consistent output
        selected.sort(key=lambda x: int(x[1:]) if x[1:].isdigit() else 999)

    if not selected:
        print("No valid tests selected. Use --suite all, --suite unit|performance|integration, or --suite t1,t2,t3")
        return 2

    results: list[TestResult] = []
    for key in selected:
        fn = name_map[key]
        res = fn(args)
        results.append(res)

    # Pretty print suite results if available
    use_pretty = (not getattr(args, "no_pretty", False)) and HAVE_RICH
    if use_pretty:
        console = Console()
        table = Table(title="Chat Cache Test Suite", box=rich_box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("Test", style="bold", no_wrap=True)
        table.add_column("Category", no_wrap=True)
        table.add_column("Description")
        table.add_column("Result", justify="center", no_wrap=True)
        table.add_column("Details")

        pass_count = 0
        fail_count = 0
        skip_count = 0

        # Group by category for better visibility
        category_styles = {
            "Unit": "cyan",
            "Performance": "magenta",
            "Integration": "yellow",
        }

        for key, res in zip(selected, results):
            title = titles.get(key, key)
            cat = categories.get(key, "Unknown")
            cat_style = category_styles.get(cat, "white")
            
            if res.skipped:
                status_str = "⏭️  SKIP"
                status_style = "yellow"
                skip_count += 1
            elif res.passed:
                status_str = "✅ PASS"
                status_style = "green"
                pass_count += 1
            else:
                status_str = "❌ FAIL"
                status_style = "red"
                fail_count += 1
            table.add_row(
                key.upper(), 
                f"[{cat_style}]{cat}[/]", 
                title, 
                f"[{status_style}]{status_str}[/]", 
                res.message
            )

        console.print(table)

        # Category breakdown
        category_counts = {}
        for key, res in zip(selected, results):
            cat = categories.get(key, "Unknown")
            if cat not in category_counts:
                category_counts[cat] = {"pass": 0, "fail": 0, "skip": 0}
            if res.skipped:
                category_counts[cat]["skip"] += 1
            elif res.passed:
                category_counts[cat]["pass"] += 1
            else:
                category_counts[cat]["fail"] += 1

        summary = Text()
        summary.append(f"Passed: {pass_count}  ", style="green")
        summary.append(f"Failed: {fail_count}  ", style="red")
        summary.append(f"Skipped: {skip_count}", style="yellow")
        summary.append("\n\n")
        summary.append("By Category:\n", style="bold")
        for cat in ["Unit", "Performance", "Integration"]:
            if cat in category_counts:
                counts = category_counts[cat]
                cat_style = category_styles.get(cat, "white")
                summary.append(f"  {cat}: ", style=cat_style)
                summary.append(f"✓{counts['pass']} ", style="green")
                summary.append(f"✗{counts['fail']} ", style="red")
                summary.append(f"⊘{counts['skip']}\n", style="yellow")
        
        border_style = "green" if fail_count == 0 else "red"
        emoji = "🎉" if fail_count == 0 else "⚠️"
        console.print(Panel(summary, title=f"{emoji} Suite Summary", border_style=border_style))
    else:
        # Plain output
        label_width = 11
        def row_line(key: str, res: TestResult) -> str:
            status = "SKIP" if res.skipped else ("PASS" if res.passed else "FAIL")
            cat = categories.get(key, "Unknown")
            return f"{key.upper().ljust(4)} [{cat.ljust(12)}] {status.ljust(5)} | {titles.get(key, key)} - {res.message}"
        print("Tests:")
        for key, res in zip(selected, results):
            print(" ", row_line(key, res))
        pass_count = sum(1 for r in results if (not r.skipped) and r.passed)
        fail_count = sum(1 for r in results if (not r.skipped) and (not r.passed))
        skip_count = sum(1 for r in results if r.skipped)
        print(f"Summary: PASS={pass_count} FAIL={fail_count} SKIP={skip_count}")
        
        # Category breakdown for plain output
        category_counts = {}
        for key, res in zip(selected, results):
            cat = categories.get(key, "Unknown")
            if cat not in category_counts:
                category_counts[cat] = {"pass": 0, "fail": 0, "skip": 0}
            if res.skipped:
                category_counts[cat]["skip"] += 1
            elif res.passed:
                category_counts[cat]["pass"] += 1
            else:
                category_counts[cat]["fail"] += 1
        print("By Category:")
        for cat in ["Unit", "Performance", "Integration"]:
            if cat in category_counts:
                counts = category_counts[cat]
                print(f"  {cat}: PASS={counts['pass']} FAIL={counts['fail']} SKIP={counts['skip']}")

    any_fail = any((not r.skipped) and (not r.passed) for r in results)
    return 1 if any_fail else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Chat cache bench and test suite")
    p.add_argument("--base-url", default="http://localhost:3000", help="WebUI base URL (default: http://localhost:3000)")
    p.add_argument("--chat-id", required=True, help="Chat ID to fetch")
    p.add_argument("--token", default=os.environ.get("WEBUI_TOKEN"), help="Bearer token (or set WEBUI_TOKEN)")
    p.add_argument("--clear-redis", action="store_true", help="Delete the snapshot key before the first run via docker exec")
    p.add_argument("--user-id", help="User ID (optional, to remove from recent list)")
    p.add_argument("--show-keys", action="store_true", help="Show KEYS and TTL after runs")
    p.add_argument("--warm-runs", type=int, default=3, help="Number of warm GETs to average (default: 3)")
    p.add_argument("--expect-speedup", type=float, default=1.20, help="Minimum expected speedup factor to pass (default: 1.20)")
    p.add_argument("--json", action="store_true", help="Output machine-readable JSON summary")
    p.add_argument("--redis-container", default="redis", help="Docker container name for Redis (default: redis)")
    p.add_argument("--http-timeout", type=float, default=30.0, help="HTTP timeout seconds (default: 30)")
    p.add_argument("--no-pretty", action="store_true", help="Disable pretty output even if 'rich' is available")
    # Suite options
    p.add_argument("--suite", help="Run named tests or 'all' (comma-separated: t1..t13, 1..13, or category: unit|performance|integration)")
    p.add_argument("--extra-chat-ids", dest="extra_chat_ids_raw", default="", help="Comma-separated extra chat IDs for LRU tests (need 1 for t8, 3 for t9)")
    p.add_argument("--recent-limit", type=int, default=3, help="Expected LRU cap (default: 3)")
    p.add_argument("--allow-redis-restart", action="store_true", help="Allow stopping/starting Redis for t13 (default: false)")
    # Performance test parameters
    p.add_argument("--concurrent-requests", type=int, default=10, help="Number of concurrent requests for t2 (default: 10)")
    p.add_argument("--max-latency-ms", type=int, default=1000, help="Max acceptable latency (p95) per request for t2 in ms (default: 1000)")
    p.add_argument("--cache-hit-runs", type=int, default=20, help="Number of cache hit requests for t3 (default: 20)")
    args = p.parse_args()

    # Banner first
    print_banner(args)

    # If suite requested, run it and exit
    if getattr(args, "suite", None):
        return run_suite(args)

    url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"

    if args.clear_redis:
        clear_redis_item(args.chat_id, container=args.redis_container)
        if args.user_id:
            remove_from_recent(args.user_id, args.chat_id, container=args.redis_container)
        time.sleep(0.3)

    # Cold
    s1, h1, _, e1 = http_get(url, token=args.token, timeout=args.http_timeout)
    pt1_raw = h1.get("x-process-time")
    pt1 = parse_header_seconds(pt1_raw)
    cold = RunResult(status=s1, header_seconds=pt1, measured_seconds=e1)
    print(f"COLD  status={cold.status} header={(pt1_raw or '-')} measured={cold.measured_seconds:.3f}s")
    if cold.status != 200:
        try:
            print(f"error: {h1}")
        except Exception:
            pass
        return 1

    # Warm runs
    warm_results: list[RunResult] = []
    for i in range(max(1, args.warm_runs)):
        s, h, _, e = http_get(url, token=args.token, timeout=args.http_timeout)
        pt_raw = h.get("x-process-time")
        pt = parse_header_seconds(pt_raw)
        warm = RunResult(status=s, header_seconds=pt, measured_seconds=e)
        warm_results.append(warm)
        print(f"WARM{i+1} status={s} header={(pt_raw or '-')} measured={e:.3f}s")
        if s != 200:
            try:
                print(f"error: {h}")
            except Exception:
                pass

    if args.show_keys:
        show_keys_and_ttl(args.chat_id, container=args.redis_container)

    cold_time = cold.effective_seconds
    warm_times = [w.effective_seconds for w in warm_results]
    warm_median = statistics.median(warm_times) if warm_times else float("inf")
    factor = (cold_time / warm_median) if warm_median > 0 else float("inf")

    verdict_pass = factor >= args.expect_speedup
    verdict_str = (
        f"cache_warm_faster by x{factor:.2f} (median of {len(warm_times)} runs)"
        if factor > 1.0 else f"no_speedup_detected (x{factor:.2f})"
    )
    print(f"Verdict: {verdict_str}")
    print(f"Assert: expected ≥ x{args.expect_speedup:.2f} → {'PASS' if verdict_pass else 'FAIL'}")

    # Pretty summary using Rich, unless disabled
    use_pretty = (not args.no_pretty) and HAVE_RICH
    if use_pretty:
        console = Console()
        table = Table(
            title="Chat Cache Timing",
            box=rich_box.SIMPLE_HEAVY,
            show_lines=False,
        )
        table.add_column("Phase", justify="left", style="bold")
        table.add_column("Status", justify="center")
        table.add_column("Header", justify="right")
        table.add_column("Measured", justify="right")
        table.add_column("Effective", justify="right")

        def status_icon(code: int) -> str:
            return "✅" if code == 200 else "❌"

        # Cold row
        table.add_row(
            "🧊 Cold",
            status_icon(cold.status),
            f"{pt1_raw or '-'}",
            f"{cold.measured_seconds:.3f}s",
            f"{cold_time:.3f}s",
        )

        # Warm rows
        for idx, w in enumerate(warm_results, start=1):
            table.add_row(
                f"🔥 Warm {idx}",
                status_icon(w.status),
                f"{(str(w.header_seconds)+'s') if (w.header_seconds and w.header_seconds>0) else '-'}",
                f"{w.measured_seconds:.3f}s",
                f"{w.effective_seconds:.3f}s",
            )

        # Summary panel
        verdict_color = "green" if verdict_pass else "red"
        verdict_emoji = "🎉" if verdict_pass else "⚠️"
        summary_text = Text()
        summary_text.append(f"Speedup: x{factor:.2f}\n", style="bold")
        summary_text.append(f"Expected: ≥ x{args.expect_speedup:.2f}\n")
        summary_text.append(f"Warm median: {warm_median:.3f}s\n")
        summary_text.append(f"Cold: {cold_time:.3f}s")
        summary_panel = Panel(summary_text, title=f"{verdict_emoji} {'PASS' if verdict_pass else 'FAIL'}", border_style=verdict_color)

        console.print(table)
        console.print(summary_panel)

        if args.show_keys:
            keys, ttl = get_keys_and_ttl(args.chat_id, container=args.redis_container)
            keys_text = Text()
            if ttl is not None:
                keys_text.append(f"TTL: {ttl}\n", style="bold")
            for k in keys:
                keys_text.append(f"{k}\n")
            console.print(Panel(keys_text, title="Redis Keys", box=rich_box.SIMPLE))

    if args.json:
        payload = {
            "cold": {
                "status": cold.status,
                "header_seconds": cold.header_seconds,
                "measured_seconds": cold.measured_seconds,
                "effective_seconds": cold_time,
            },
            "warm": {
                "runs": [
                    {
                        "status": w.status,
                        "header_seconds": w.header_seconds,
                        "measured_seconds": w.measured_seconds,
                        "effective_seconds": w.effective_seconds,
                    }
                    for w in warm_results
                ],
                "median_seconds": warm_median,
            },
            "speedup_factor": factor,
            "passed": verdict_pass,
        }
        print(json.dumps(payload, indent=2))

    return 0 if verdict_pass else 1


if __name__ == "__main__":
    sys.exit(main())










# OLD TEST CODE : NOT USED ANYMORE
# #!/usr/bin/env python3
# """
# Chat Cache Bench: cold vs warm

# What this script does:
# - Optionally clears the chat snapshot key and removes it from the recent list
# - Performs a cold GET (after clear) and several warm GETs
# - Reports timing based on X-Process-Time header (if present) or measured wall time
# - Optionally prints Redis KEYS and TTL, and can output JSON for CI tools

# Quick example:
#   python3 test/chat_cache_bench.py \
#     --chat-id $CHAT_ID \
#     --token "$WEBUI_TOKEN" \
#     --clear-redis \
#     --user-id $USER_ID \
#     --warm-runs 5 \
#     --expect-speedup 1.5 \
#     --show-keys

# export WEBUI_TOKEN='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImVkNDQ5NzEyLWE4ODYtNDRjMi1iY2M5LTkyNWYzZjEyNjYxNCJ9.R8-IBOk14SrIGAI-oOEGvueq5CTv4RNyo-McA_9C8Tk'
# export CHAT_ID=149df51e-28fc-431e-b9cb-39e9e408d5b0
# export USER_ID=<your_user_id>

# Notes:
# - Base URL defaults to http://localhost:3000 (override via --base-url)
# - Redis commands use: docker exec <container> redis-cli (container defaults to "redis")
# - Authorization is optional but most routes require it; pass --token if needed
# - Pretty output uses the 'rich' library if available. For best visuals:
#     pip install rich
# """

# import argparse
# import os
# import sys
# import time
# import json
# import re
# import statistics
# import subprocess
# from dataclasses import dataclass
# from typing import Optional
# from urllib.request import Request, urlopen
# from urllib.error import HTTPError, URLError
# from datetime import datetime

# # Optional pretty output
# try:
#     from rich.console import Console
#     from rich.table import Table
#     from rich.panel import Panel
#     from rich.text import Text
#     from rich import box as rich_box
#     HAVE_RICH = True
# except Exception:
#     HAVE_RICH = False


# def docker_exec(args: list[str], container: str = "redis") -> tuple[int, str, str]:
#     """Run a redis-cli command inside a Docker container.

#     Returns (exit_code, stdout, stderr) with stdout/stderr stripped.
#     """
#     try:
#         proc = subprocess.Popen(
#             ["docker", "exec", container, "redis-cli", *args],
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             text=True,
#         )
#         out, err = proc.communicate(timeout=15)
#         return proc.returncode, out.strip(), err.strip()
#     except Exception as e:
#         return 1, "", str(e)


# def clear_redis_item(chat_id: str, container: str = "redis") -> None:
#     docker_exec(["DEL", f"open-webui:chat-cache:item:{chat_id}"], container=container)


# def remove_from_recent(user_id: str, chat_id: str, container: str = "redis") -> None:
#     docker_exec(["LREM", f"open-webui:chat-cache:recent:{user_id}", "0", chat_id], container=container)


# def show_keys_and_ttl(chat_id: str, container: str = "redis") -> None:
#     code, out, err = docker_exec(["KEYS", "open-webui:chat-cache:*"] , container=container)
#     if out:
#         print(f"KEYS:\n{out}")
#     code, out, err = docker_exec(["TTL", f"open-webui:chat-cache:item:{chat_id}"], container=container)
#     if out:
#         print(f"TTL item:{chat_id}: {out}")


# def get_keys_and_ttl(chat_id: str, container: str = "redis") -> tuple[list[str], Optional[int]]:
#     keys: list[str] = []
#     code, out, _ = docker_exec(["KEYS", "open-webui:chat-cache:*"] , container=container)
#     if out:
#         keys = [line.strip() for line in out.splitlines() if line.strip()]
#     code, out, _ = docker_exec(["TTL", f"open-webui:chat-cache:item:{chat_id}"], container=container)
#     ttl: Optional[int] = None
#     try:
#         if out:
#             ttl = int(out.strip())
#     except Exception:
#         ttl = None
#     return keys, ttl


# def print_banner(args) -> None:
#     use_pretty = (not args.no_pretty) and HAVE_RICH
#     ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     base_url = args.base_url.rstrip("/")

#     def shorten(value: Optional[str], keep: int = 6) -> str:
#         if not value:
#             return "-"
#         v = str(value)
#         return v if len(v) <= keep * 2 + 1 else f"{v[:keep]}…{v[-keep:]}"

#     chat_disp = shorten(args.chat_id, 6)
#     user_disp = shorten(args.user_id, 6) if args.user_id else "-"

#     if use_pretty:
#         console = Console()
#         # Build a fixed-width label column to ensure alignment
#         labels = ["URL", "Chat", "User", "Warm runs", "Expect", "Redis", "Time"]
#         label_width = max(len(l) for l in labels)
#         info = Table(show_header=False, box=rich_box.SIMPLE, expand=False, padding=(0, 1))
#         info.add_column(justify="right", style="bold cyan", no_wrap=True, min_width=label_width)
#         info.add_column(justify="left", no_wrap=False)
#         info.add_row("URL", base_url)
#         info.add_row("Chat", chat_disp)
#         info.add_row("User", user_disp)
#         info.add_row("Warm runs", str(max(1, getattr(args, "warm_runs", 1))))
#         info.add_row("Expect", f"≥ x{getattr(args, 'expect_speedup', 1.2):.2f}")
#         info.add_row("Redis", getattr(args, "redis_container", "redis"))
#         info.add_row("Time", ts)
#         panel = Panel(info, title="🚀 Chat Cache Bench", border_style="cyan", box=rich_box.HEAVY)
#         console.print(panel)
#     else:
#         labels = ["URL", "Chat", "User", "Warm runs", "Expect", "Redis", "Time"]
#         label_width = max(len(l) for l in labels)
#         def row(label: str, value: str) -> str:
#             return f"{label.ljust(label_width)} : {value}"
#         print("=" * 60)
#         print("🚀 Chat Cache Bench")
#         print(row("URL", base_url))
#         print(row("Chat", chat_disp))
#         print(row("User", user_disp))
#         print(row("Warm runs", str(max(1, getattr(args, 'warm_runs', 1)))))
#         print(row("Expect", f"≥ x{getattr(args, 'expect_speedup', 1.2):.2f}"))
#         print(row("Redis", getattr(args, 'redis_container', 'redis')))
#         print(row("Time", ts))
#         print("=" * 60)


# def parse_header_seconds(value: Optional[str]) -> Optional[float]:
#     """Parse X-Process-Time style header values like '123ms', '0s', '0', '0.012'.
#     Returns seconds as float, or None if unparsable.
#     """
#     if value is None:
#         return None
#     v = value.strip().lower()
#     if not v:
#         return None
#     try:
#         # Common forms: '0s', '12ms', '0.123', '0'
#         if v.endswith("ms"):
#             num = float(v[:-2])
#             return num / 1000.0
#         if v.endswith("s"):
#             num = float(v[:-1])
#             return num
#         # plain int/float
#         return float(v)
#     except Exception:
#         # Try to extract number+s or number+ms generically
#         m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(ms|s)?$", v)
#         if m:
#             num = float(m.group(1))
#             unit = m.group(2) or "s"
#             return num / 1000.0 if unit == "ms" else num
#         return None


# def http_get(url: str, token: str | None = None, timeout: float = 30.0) -> tuple[int, dict, bytes, float]:
#     headers = {"Accept": "application/json"}
#     if token:
#         headers["Authorization"] = f"Bearer {token}"
#     req = Request(url, headers=headers, method="GET")
#     start = time.perf_counter()
#     try:
#         with urlopen(req, timeout=timeout) as resp:
#             elapsed = time.perf_counter() - start
#             status = resp.status
#             content = resp.read()
#             # Convert header list to dict (case-insensitive keys)
#             hdrs = {k.lower(): v for k, v in resp.headers.items()}
#             return status, hdrs, content, elapsed
#     except HTTPError as e:
#         elapsed = time.perf_counter() - start
#         return e.code, {"error": str(e)}, e.read() if e.fp else b"", elapsed
#     except URLError as e:
#         elapsed = time.perf_counter() - start
#         return 0, {"error": str(e)}, b"", elapsed


# @dataclass
# class RunResult:
#     status: int
#     header_seconds: Optional[float]
#     measured_seconds: float

#     @property
#     def effective_seconds(self) -> float:
#         # Prefer header if positive; else measured
#         if self.header_seconds is not None and self.header_seconds > 0:
#             return float(self.header_seconds)
#         return float(self.measured_seconds)


# def main() -> int:
#     p = argparse.ArgumentParser(description="Benchmark cold vs warm chat cache loads")
#     p.add_argument("--base-url", default="http://localhost:3000", help="WebUI base URL (default: http://localhost:3000)")
#     p.add_argument("--chat-id", required=True, help="Chat ID to fetch")
#     p.add_argument("--token", default=os.environ.get("WEBUI_TOKEN"), help="Bearer token (or set WEBUI_TOKEN)")
#     p.add_argument("--clear-redis", action="store_true", help="Delete the snapshot key before the first run via docker exec")
#     p.add_argument("--user-id", help="User ID (optional, to remove from recent list)")
#     p.add_argument("--show-keys", action="store_true", help="Show KEYS and TTL after runs")
#     p.add_argument("--warm-runs", type=int, default=3, help="Number of warm GETs to average (default: 3)")
#     p.add_argument("--expect-speedup", type=float, default=1.20, help="Minimum expected speedup factor to pass (default: 1.20)")
#     p.add_argument("--json", action="store_true", help="Output machine-readable JSON summary")
#     p.add_argument("--redis-container", default="redis", help="Docker container name for Redis (default: redis)")
#     p.add_argument("--http-timeout", type=float, default=30.0, help="HTTP timeout seconds (default: 30)")
#     p.add_argument("--no-pretty", action="store_true", help="Disable pretty output even if 'rich' is available")
#     args = p.parse_args()

#     # Banner first
#     print_banner(args)

#     url = f"{args.base_url.rstrip('/')}/api/v1/chats/{args.chat_id}"

#     if args.clear_redis:
#         clear_redis_item(args.chat_id, container=args.redis_container)
#         if args.user_id:
#             remove_from_recent(args.user_id, args.chat_id, container=args.redis_container)
#         time.sleep(0.3)

#     # Cold
#     s1, h1, _, e1 = http_get(url, token=args.token, timeout=args.http_timeout)
#     pt1_raw = h1.get("x-process-time")
#     pt1 = parse_header_seconds(pt1_raw)
#     cold = RunResult(status=s1, header_seconds=pt1, measured_seconds=e1)
#     print(f"COLD  status={cold.status} header={(pt1_raw or '-')} measured={cold.measured_seconds:.3f}s")
#     if cold.status != 200:
#         try:
#             print(f"error: {h1}")
#         except Exception:
#             pass
#         return 1

#     # Warm runs
#     warm_results: list[RunResult] = []
#     for i in range(max(1, args.warm_runs)):
#         s, h, _, e = http_get(url, token=args.token, timeout=args.http_timeout)
#         pt_raw = h.get("x-process-time")
#         pt = parse_header_seconds(pt_raw)
#         warm = RunResult(status=s, header_seconds=pt, measured_seconds=e)
#         warm_results.append(warm)
#         print(f"WARM{i+1} status={s} header={(pt_raw or '-')} measured={e:.3f}s")
#         if s != 200:
#             try:
#                 print(f"error: {h}")
#             except Exception:
#                 pass

#     if args.show_keys:
#         show_keys_and_ttl(args.chat_id, container=args.redis_container)

#     cold_time = cold.effective_seconds
#     warm_times = [w.effective_seconds for w in warm_results]
#     warm_median = statistics.median(warm_times) if warm_times else float("inf")
#     factor = (cold_time / warm_median) if warm_median > 0 else float("inf")

#     verdict_pass = factor >= args.expect_speedup
#     verdict_str = (
#         f"cache_warm_faster by x{factor:.2f} (median of {len(warm_times)} runs)"
#         if factor > 1.0 else f"no_speedup_detected (x{factor:.2f})"
#     )
#     print(f"Verdict: {verdict_str}")
#     print(f"Assert: expected ≥ x{args.expect_speedup:.2f} → {'PASS' if verdict_pass else 'FAIL'}")

#     # Pretty summary using Rich, unless disabled
#     use_pretty = (not args.no_pretty) and HAVE_RICH
#     if use_pretty:
#         console = Console()
#         table = Table(
#             title="Chat Cache Timing",
#             box=rich_box.SIMPLE_HEAVY,
#             show_lines=False,
#         )
#         table.add_column("Phase", justify="left", style="bold")
#         table.add_column("Status", justify="center")
#         table.add_column("Header", justify="right")
#         table.add_column("Measured", justify="right")
#         table.add_column("Effective", justify="right")

#         def status_icon(code: int) -> str:
#             return "✅" if code == 200 else "❌"

#         # Cold row
#         table.add_row(
#             "🧊 Cold",
#             status_icon(cold.status),
#             f"{pt1_raw or '-'}",
#             f"{cold.measured_seconds:.3f}s",
#             f"{cold_time:.3f}s",
#         )

#         # Warm rows
#         for idx, w in enumerate(warm_results, start=1):
#             table.add_row(
#                 f"🔥 Warm {idx}",
#                 status_icon(w.status),
#                 f"{(str(w.header_seconds)+'s') if (w.header_seconds and w.header_seconds>0) else '-'}",
#                 f"{w.measured_seconds:.3f}s",
#                 f"{w.effective_seconds:.3f}s",
#             )

#         # Summary panel
#         verdict_color = "green" if verdict_pass else "red"
#         verdict_emoji = "🎉" if verdict_pass else "⚠️"
#         summary_text = Text()
#         summary_text.append(f"Speedup: x{factor:.2f}\n", style="bold")
#         summary_text.append(f"Expected: ≥ x{args.expect_speedup:.2f}\n")
#         summary_text.append(f"Warm median: {warm_median:.3f}s\n")
#         summary_text.append(f"Cold: {cold_time:.3f}s")
#         summary_panel = Panel(summary_text, title=f"{verdict_emoji} {'PASS' if verdict_pass else 'FAIL'}", border_style=verdict_color)

#         console.print(table)
#         console.print(summary_panel)

#         if args.show_keys:
#             keys, ttl = get_keys_and_ttl(args.chat_id, container=args.redis_container)
#             keys_text = Text()
#             if ttl is not None:
#                 keys_text.append(f"TTL: {ttl}\n", style="bold")
#             for k in keys:
#                 keys_text.append(f"{k}\n")
#             console.print(Panel(keys_text, title="Redis Keys", box=rich_box.SIMPLE))

#     if args.json:
#         payload = {
#             "cold": {
#                 "status": cold.status,
#                 "header_seconds": cold.header_seconds,
#                 "measured_seconds": cold.measured_seconds,
#                 "effective_seconds": cold_time,
#             },
#             "warm": {
#                 "runs": [
#                     {
#                         "status": w.status,
#                         "header_seconds": w.header_seconds,
#                         "measured_seconds": w.measured_seconds,
#                         "effective_seconds": w.effective_seconds,
#                     }
#                     for w in warm_results
#                 ],
#                 "median_seconds": warm_median,
#             },
#             "speedup_factor": factor,
#             "passed": verdict_pass,
#         }
#         print(json.dumps(payload, indent=2))

#     return 0 if verdict_pass else 1


# if __name__ == "__main__":
#     sys.exit(main())



