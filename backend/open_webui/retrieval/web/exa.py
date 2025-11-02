import os, asyncio, random, logging, httpx
from typing import List, Optional, Dict, Callable
from .engine_template import template_variant_engine, log as core_log
from open_webui.retrieval.web.main import SearchResult

ENGINE_NAME = "exa"

log = logging.getLogger(__name__)

def _gen_variants(q: str, n: int = 4) -> List[str]:
    q = (q or "").strip()
    if not q:
        return []
    base = [q, f"\"{q}\"", f"{q} news", f"{q} tutorial"]
    out, seen = [], set()
    for s in base:
        if s and s not in seen:
            seen.add(s); out.append(s)
        if len(out) >= n:
            break
    return out

async def _exa_once(
    client: httpx.AsyncClient,
    query: str,
    count: int,
    timeout: float,
    *,
    api_key: str,
    api_base: str,
    attempt: int = 0,
    max_attempts: int = 3,
) -> List[Dict]:
    if not api_key:
        raise RuntimeError("[exa] EXA_API_KEY not set")

    url = f"{api_base.rstrip('/')}/search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "numResults": max(1, min(int(count), 10)),
        "contents": {"text": True, "highlights": True},
        "type": "auto",
    }

    for method in ("POST", "GET"):
        try:
            if method == "POST":
                r = await client.post(url, headers=headers, json=payload, timeout=timeout)
            else:
                r = await client.get(url, headers=headers, params=payload, timeout=timeout)
        except Exception as ex:
            if attempt + 1 < max_attempts:
                backoff = (1.0 * (2 ** attempt)) + random.uniform(0.2, 0.8)
                core_log.warning(
                    f"[{ENGINE_NAME}] connect error | method={method} retry_in={backoff:.1f}s "
                    f"attempt={attempt+1}/{max_attempts-1} err={ex}"
                )
                await asyncio.sleep(backoff)
                return await _exa_once(
                    client, query, count, timeout,
                    api_key=api_key, api_base=api_base,
                    attempt=attempt+1, max_attempts=max_attempts
                )
            core_log.warning(f"[{ENGINE_NAME}] connect final fail | method={method} err={ex}")
            continue

        if r.status_code in (401, 403):
            core_log.warning(f"[{ENGINE_NAME}] {r.status_code} auth error | body={(r.text or '')[:200]!r}")
            continue
        if r.status_code == 404:
            core_log.warning(f"[{ENGINE_NAME}] 404 path not found | method={method} body={(r.text or '')[:200]!r}")
            continue
        if r.status_code == 429:
            if attempt + 1 < max_attempts:
                backoff = (1.0 * (2 ** attempt)) + random.uniform(0.2, 0.8)
                core_log.warning(
                    f"[{ENGINE_NAME}] 429 rate limit | retry_in={backoff:.1f}s attempt={attempt+1}/{max_attempts-1}"
                )
                await asyncio.sleep(backoff)
                return await _exa_once(
                    client, query, count, timeout,
                    api_key=api_key, api_base=api_base,
                    attempt=attempt+1, max_attempts=max_attempts
                )
            core_log.warning(f"[{ENGINE_NAME}] 429 final fail")
            continue

        try:
            r.raise_for_status()
        except httpx.HTTPStatusError:
            if attempt + 1 < max_attempts:
                backoff = (1.0 * (2 ** attempt)) + random.uniform(0.2, 0.8)
                core_log.warning(
                    f"[{ENGINE_NAME}] {r.status_code} | retry_in={backoff:.1f}s attempt={attempt+1}/{max_attempts-1} "
                    f"body={(r.text or '')[:200]!r}"
                )
                await asyncio.sleep(backoff)
                return await _exa_once(
                    client, query, count, timeout,
                    api_key=api_key, api_base=api_base,
                    attempt=attempt+1, max_attempts=max_attempts
                )
            core_log.warning(f"[{ENGINE_NAME}] final HTTP fail | status={r.status_code} body={(r.text or '')[:200]!r}")
            continue

        data = r.json() or {}
        items = (data.get("results") or [])[:count]
        out: List[Dict] = []
        for it in items:
            url_i = (it.get("url") or "").strip()
            if not url_i:
                continue
            out.append({
                "title": it.get("title") or url_i,
                "url": url_i,
                "snippet": (it.get("text") or "")[:500],
                "source": ENGINE_NAME,
            })
        return out

    return []

MAX_LIMIT = 100
MAX_CONCURRENCY = 10
DEFAULT_LIMIT = 30 
DEFAULT_CONCURRENCY = 3 

async def search_many_links(
    q: str,
    limit: int = DEFAULT_LIMIT,
    timeout: float = 10.0,
    page_size: int = 10,
    max_page_concurrency: int = DEFAULT_CONCURRENCY,
    max_variant_concurrency: int = 3,                          
    filter_list: Optional[List[str]] = None,
    *,
    api_key: Optional[str] = None, 
    api_base: Optional[str] = None, 
) -> List[SearchResult]:
    
    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY)) 
    
    key = (api_key or os.getenv("EXA_API_KEY") or "").strip()
    base = (api_base or os.getenv("EXA_API_BASE") or "https://api.exa.ai").strip()
    if not key:
        raise RuntimeError("[exa] EXA_API_KEY not set")

    concurrency = (
        3 if (max_variant_concurrency is None and max_page_concurrency is None)
        else max(1, min(v for v in (max_page_concurrency, max_variant_concurrency) if v is not None))
    )

    async def _bound_fetch(
        client: httpx.AsyncClient,
        query: str,
        count: int,
        t: float,
        attempt: int = 0,
        max_attempts: int = 3,
    ):
        return await _exa_once(
            client=client,
            query=query,
            count=count,
            timeout=t,
            api_key=key,
            api_base=base,
            attempt=attempt,
            max_attempts=max_attempts,
        )

    return await template_variant_engine(
        q=q,
        limit=limit,
        per_variant=max(1, min(int(page_size), 10)),
        fetch_once_fn=_bound_fetch, 
        gen_variants_fn=_gen_variants,
        engine_name=ENGINE_NAME,
        timeout=timeout,
        max_variant_concurrency=concurrency,
        filter_list=filter_list,
        n_variants=4,
    )
