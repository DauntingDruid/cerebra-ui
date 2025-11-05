import asyncio, httpx, math, logging, uuid, statistics
from typing import List, Dict, Optional, Callable, Awaitable
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from open_webui.retrieval.web.main import SearchResult, get_filtered_results

import re

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
URL_RE     = re.compile(r"https?://\S+")
WS_RE      = re.compile(r"\s+")

def _clean_snippet(s: str) -> str:
    if not s:
        return ""
    s = MD_LINK_RE.sub(r"\1", s)
    s = URL_RE.sub("", s)
    s = WS_RE.sub(" ", s).strip()
    return s

def _truncate_snippet(s: str, max_len: int = 220) -> str:
    if not s:
        return ""
    is_zh = any("\u4e00" <= ch <= "\u9fff" for ch in s)
    if is_zh:
        parts = re.split(r"[。！？…]+", s)
        s = "。".join(p for p in parts[:2] if p)
    else:
        parts = re.split(r"(?<=[\.!?])\s+", s)
        if len(parts) >= 2:
            s = " ".join(parts[:2])

    if len(s) <= max_len:
        return s
    cut = s.rfind(" ", 0, max_len - 1) if not is_zh else -1
    cut = cut if cut != -1 else max_len
    return s[:cut].rstrip() + "…"

log = logging.getLogger("web.search")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d - %(message)s"
    ))
    log.addHandler(_h)
log.setLevel(logging.INFO)
log.propagate = False

def norm_url(u: str) -> str:
    p = urlparse(u or "")
    q = tuple(sorted((k, v) for k, v in parse_qsl(p.query) if not k.startswith("utm_")))
    return urlunparse(p._replace(query=urlencode(q), fragment="")).rstrip("/")

def dedupe_keep_order(items: List[Dict], keyfunc):
    seen, out = set(), []
    for it in items:
        k = keyfunc(it)
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out

def _postprocess_to_SearchResult(rows: List[Dict], filter_list=None, max_snippet: int = 220) -> List[SearchResult]:
    if filter_list:
        rows = get_filtered_results(rows, filter_list)
    rows = dedupe_keep_order(rows, keyfunc=lambda x: norm_url(x.get("url", "")))
    out: List[SearchResult] = []
    for r in rows:
        title = r.get("title") or r.get("url") or ""
        url   = r.get("url") or ""
        sn    = _truncate_snippet(_clean_snippet(r.get("snippet") or ""), max_snippet)
        if url:
            out.append(SearchResult(link=url, title=title, snippet=sn))
    return out

FetchFn = Callable[[httpx.AsyncClient, str, int, int, float], Awaitable[List[Dict]]]

async def template_paged_engine(
    q: str,
    limit: int,
    page_size: int,
    fetch_page_fn: FetchFn,
    engine_name: str,
    timeout: float = 10.0,
    max_page_concurrency: int = 3,
    filter_list: Optional[List[str]] = None,
) -> List[SearchResult]:
    limit = max(1, int(limit))
    page_size = max(1, int(page_size))
    max_page_concurrency = max(1, int(max_page_concurrency))

    total_pages = max(1, math.ceil(limit / page_size))
    sem = asyncio.Semaphore(max_page_concurrency)

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    run_id = uuid.uuid4().hex[:6]

    timing = {
        "pages": total_pages,
        "durations": [],
        "queue_waits": [],
        "starts": [],
        "ends": [],
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def one(p: int):
            t_enq = loop.time()
            log.info(f"[{engine_name}#{run_id}] page {p} ENQ +{t_enq - t0:.2f}s")

            async with sem:
                
                t_acq = loop.time()
                qwait = t_acq - t_enq
                log.info(f"[{engine_name}#{run_id}] page {p} START +{t_acq - t0:.2f}s (queue_wait={qwait:.2f}s)")

                try:
                    r = await fetch_page_fn(client, q, p, page_size, timeout)
                    
                    t_end = loop.time()
                    dur = t_end - t_acq
                    log.info(f"[{engine_name}#{run_id}] page {p} DONE  +{t_end - t0:.2f}s (dur={dur:.2f}s)")

                    timing["durations"].append(dur)
                    timing["queue_waits"].append(qwait)
                    timing["starts"].append(t_acq - t0)
                    timing["ends"].append(t_end - t0)
                    return r or []
                except Exception:
                    t_end = loop.time()
                    log.exception(f"[{engine_name}#{run_id}] page {p} FAIL  +{t_end - t0:.2f}s")
                    timing["queue_waits"].append(qwait)
                    timing["starts"].append(t_acq - t0)
                    timing["ends"].append(t_end - t0)
                    return []

        batches = await asyncio.gather(*[asyncio.create_task(one(p)) for p in range(1, total_pages + 1)])

    t1 = loop.time()
    wall = t1 - t0

    if timing["durations"]:
        sum_dur = sum(timing["durations"])
        max_dur = max(timing["durations"])
        p95 = statistics.quantiles(timing["durations"], n=20)[-1] if len(timing["durations"]) >= 2 else timing["durations"][0]
        avg_q = sum(timing["queue_waits"]) / max(1, len(timing["queue_waits"]))
 
        log.info(
                f"[{engine_name}#{run_id}] SUMMARY pages={total_pages} "
                f"wall={wall:.2f}s sum_dur={sum_dur:.2f}s max_dur={max_dur:.2f}s "
                f"p95_page={p95:.2f}s avg_queue_wait={avg_q:.2f}s "
                f"(max_conc={max_page_concurrency})"
            )
    else:
        log.info(f"[{engine_name}#{run_id}] SUMMARY pages={total_pages} wall={wall:.2f}s (no pages)")

    flat = [x for b in batches if b for x in b][:limit]
    return _postprocess_to_SearchResult(flat, filter_list)

FetchOnceFn = Callable[[httpx.AsyncClient, str, int, float], Awaitable[List[Dict]]]
GenVariantsFn = Callable[[str, int], List[str]]

async def template_variant_engine(
    q: str,
    limit: int,
    per_variant: int,
    fetch_once_fn: FetchOnceFn,
    gen_variants_fn: GenVariantsFn,
    engine_name: str,
    timeout: float = 10.0,
    max_variant_concurrency: int = 3,
    filter_list: Optional[List[str]] = None,
    n_variants: int = 4,
) -> List[SearchResult]:
    limit = max(1, int(limit))
    per_variant = max(1, int(per_variant))
    max_variant_concurrency = max(1, int(max_variant_concurrency))

    variants = gen_variants_fn(q, n_variants)
    if not variants:
        return []

    sem = asyncio.Semaphore(max_variant_concurrency)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    run_id = uuid.uuid4().hex[:6]

    timing = {"durations": [], "queue_waits": [], "starts": [], "ends": []}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def one(vq: str, idx: int):
            t_enq = loop.time()
            log.info(f"[{engine_name}#{run_id}] var{idx} ENQ +{t_enq - t0:.2f}s q={vq!r}")
            
            await asyncio.sleep(0.05 * (idx % max_variant_concurrency))
            async with sem:
                t_acq = loop.time()
                qwait = t_acq - t_enq
                log.info(f"[{engine_name}#{run_id}] var{idx} START +{t_acq - t0:.2f}s (queue_wait={qwait:.2f}s) q={vq!r}")
                try:
                    r = await fetch_once_fn(client, vq, per_variant, timeout)
                    t_end = loop.time()
                    dur = t_end - t_acq
                    log.info(f"[{engine_name}#{run_id}] var{idx} DONE  +{t_end - t0:.2f}s (dur={dur:.2f}s) got={len(r or [])}")
                    timing["durations"].append(dur)
                    timing["queue_waits"].append(qwait)
                    timing["starts"].append(t_acq - t0)
                    timing["ends"].append(t_end - t0)
                    return r or []
                except Exception:
                    t_end = loop.time()
                    log.exception(f"[{engine_name}#{run_id}] var{idx} FAIL  +{t_end - t0:.2f}s q={vq!r}")
                    timing["queue_waits"].append(qwait)
                    timing["starts"].append(t_acq - t0)
                    timing["ends"].append(t_end - t0)
                    return []

        pages = await asyncio.gather(*[asyncio.create_task(one(v, i)) for i, v in enumerate(variants)])

    wall = loop.time() - t0
    if timing["durations"]:
        sum_dur = sum(timing["durations"])
        max_dur = max(timing["durations"])
        p95 = statistics.quantiles(timing["durations"], n=20)[-1] if len(timing["durations"]) >= 2 else timing["durations"][0]
        avg_q = sum(timing["queue_waits"]) / max(1, len(timing["queue_waits"]))
        log.info(
            f"[{engine_name}#{run_id}] SUMMARY variants={len(variants)} "
            f"wall={wall:.2f}s sum_dur={sum_dur:.2f}s max_dur={max_dur:.2f}s "
            f"p95_var={p95:.2f}s avg_queue_wait={avg_q:.2f}s "
            f"(max_var_conc={max_variant_concurrency})"
        )
    else:
        log.info(f"[{engine_name}#{run_id}] SUMMARY variants={len(variants)} wall={wall:.2f}s (no variants)")

    flat = [x for b in pages if b for x in b][:limit]
    return _postprocess_to_SearchResult(flat, filter_list) 
