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


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark cold vs warm chat cache loads")
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
    args = p.parse_args()

    # Banner first
    print_banner(args)

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


