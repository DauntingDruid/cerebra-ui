import os, asyncio, logging, random, httpx
from typing import List, Optional, Dict
from .engine_template import template_variant_engine, log as core_log
from open_webui.retrieval.web.main import SearchResult

ENGINE_NAME = "jina"
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


async def _jina_once_impl(
    client: httpx.AsyncClient,
    query: str,
    count: int,
    timeout: float,
    *,
    api_key: str,
    endpoints: List[str],
    verbose: bool,
) -> List[Dict]:

    if not api_key:
        raise RuntimeError(f"[{ENGINE_NAME}] JINA_API_KEY not set")

    auth_styles = ("bearer", "plain", "x-api-key")
    methods = ("POST", "GET")

    def _headers(style: str) -> dict:
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Retain-Images": "none",
        }
        if style == "bearer":
            h["Authorization"] = f"Bearer {api_key}"
        elif style == "plain":
            h["Authorization"] = api_key
        elif style == "x-api-key":
            h["X-API-Key"] = api_key
        return h

    payload = {"q": query, "count": max(1, min(int(count), 10))}

    max_attempts = 3
    for ep in endpoints:
        for style in auth_styles:
            headers = _headers(style)
            for method in methods:
                for attempt in range(max_attempts):
                    try:
                        if method == "POST":
                            r = await client.post(ep, headers=headers, json=payload, timeout=timeout)
                        else:
                            r = await client.get(ep, headers=headers, params=payload, timeout=timeout)
                    except Exception as ex:
                        if attempt < max_attempts - 1:
                            backoff = (1.0 * (2 ** attempt)) + random.uniform(0.2, 0.8)
                            if verbose:
                                core_log.warning(
                                    f"[{ENGINE_NAME}] connect err | ep={ep} auth={style} {method} "
                                    f"retry_in={backoff:.1f}s"
                                )
                            await asyncio.sleep(backoff)
                            continue
                        if verbose:
                            core_log.warning(
                                f"[{ENGINE_NAME}] connect final fail | ep={ep} auth={style} {method} err={ex}"
                            )
                        break

                    if r.status_code == 404:
                        if verbose:
                            core_log.warning(
                                f"[{ENGINE_NAME}] 404 | ep={ep} auth={style} {method} "
                                f"body={(r.text or '')[:200]!r}"
                            )
                        break
                    if r.status_code in (401, 403):
                        if verbose:
                            core_log.warning(f"[{ENGINE_NAME}] {r.status_code} auth | ep={ep} auth={style} {method}")
                        break
                    if r.status_code == 429 and attempt < max_attempts - 1:
                        backoff = (1.0 * (2 ** attempt)) + random.uniform(0.2, 0.8)
                        if verbose:
                            core_log.warning(
                                f"[{ENGINE_NAME}] 429 | ep={ep} auth={style} {method} retry_in={backoff:.1f}s"
                            )
                        await asyncio.sleep(backoff)
                        continue

                    try:
                        r.raise_for_status()
                    except httpx.HTTPStatusError:
                        if attempt < max_attempts - 1:
                            backoff = (1.0 * (2 ** attempt)) + random.uniform(0.2, 0.8)
                            if verbose:
                                core_log.warning(
                                    f"[{ENGINE_NAME}] {r.status_code} | ep={ep} auth={style} {method} "
                                    f"retry_in={backoff:.1f}s"
                                )
                            await asyncio.sleep(backoff)
                            continue
                        if verbose:
                            core_log.warning(
                                f"[{ENGINE_NAME}] final HTTP fail | status={r.status_code} "
                                f"body={(r.text or '')[:200]!r}"
                            )
                        break

                    data = r.json() or {}
                    items = data.get("data") or data.get("results") or []
                    out: List[Dict] = []
                    for it in items:
                        url_i = (it.get("url") or "").strip()
                        if not url_i:
                            continue
                        out.append({
                            "title": it.get("title") or url_i,
                            "url": url_i,
                            "snippet": it.get("content") or "",
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
    max_variant_concurrency: Optional[int] = None,
    filter_list: Optional[List[str]] = None,
    *,
    api_key: Optional[str] = None, 
    endpoint: Optional[str] = None, 
    verbose: bool = False, 
) -> List[SearchResult]:
    
    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY)) 

    key = (api_key or os.getenv("JINA_API_KEY") or "").strip()
    env_ep = (os.getenv("JINA_SEARCH_ENDPOINT") or "").strip()
    endpoints = [e for e in [
        endpoint,
        env_ep,
        "https://s.jina.ai/search",
        "https://s.jina.ai/",
        "https://api.jina.ai/v1/search",
        "https://api.jina.ai/search",
    ] if e]

    concurrency = (
        3 if (max_variant_concurrency is None and max_page_concurrency is None)
        else max(1, min(v for v in (max_page_concurrency, max_variant_concurrency) if v is not None))
    )

    async def _fetch(client: httpx.AsyncClient, query_: str, count_: int, timeout_: float):
        return await _jina_once_impl(
            client=client,
            query=query_,
            count=count_,
            timeout=timeout_,
            api_key=key,
            endpoints=endpoints,
            verbose=verbose,
        )

    return await template_variant_engine(
        q=q,
        limit=limit,
        per_variant=max(1, min(int(page_size), 10)),
        fetch_once_fn=_fetch,         
        gen_variants_fn=_gen_variants,
        engine_name=ENGINE_NAME,
        timeout=timeout,
        max_variant_concurrency=concurrency,
        filter_list=filter_list,
        n_variants=4,
    )
