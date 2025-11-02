import os, httpx
from typing import List, Dict, Optional
from .engine_template import template_variant_engine
from open_webui.retrieval.web.main import SearchResult

ENGINE_NAME = "tavily"

_TAVILY_KEY_ENV = os.getenv("TAVILY_API_KEY") or os.getenv("TAVILY_KEY")
_DEFAULT_ENDPOINT = os.getenv("TAVILY_ENDPOINT", "https://api.tavily.com/search")
_DEFAULT_DEPTH_ENV = (os.getenv("TAVILY_EXTRACT_DEPTH") or os.getenv("TAVILY_SEARCH_DEPTH") or "").strip().lower()

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

def _norm_depth(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    d = v.strip().lower()
    if d in {"basic", "advanced"}:
        return d
    return None

async def _tavily_once_impl(
    client: httpx.AsyncClient,
    query: str,
    per_variant: int,
    timeout: float,
    *,
    api_key: str,
    endpoint: str,
    search_depth: Optional[str] = None, 
) -> List[Dict]:
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not set")

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max(1, int(per_variant)),
    }
    d = _norm_depth(search_depth)
    if d:
        payload["search_depth"] = d

    headers = {"Accept": "application/json", "User-Agent": "OpenWebUI-Search/1.0"}

    r = await client.post(endpoint, json=payload, headers=headers, timeout=timeout)
    if r.status_code in (401, 403):
        raise RuntimeError(f"[{ENGINE_NAME}] Unauthorized/Forbidden")
    if r.status_code == 429:
        raise RuntimeError(f"[{ENGINE_NAME}] Rate limited (429)")
    r.raise_for_status()

    data = r.json() or {}
    items = data.get("results") or []

    out: List[Dict] = []
    for it in items[: payload["max_results"]]:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        out.append({
            "title": it.get("title") or url,
            "url": url,
            "snippet": it.get("content") or "",
            "source": ENGINE_NAME,
        })
    return out

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
    search_depth: Optional[str] = None,
) -> List[SearchResult]:
    
    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY)) 

    key = api_key or _TAVILY_KEY_ENV
    ep = (endpoint or _DEFAULT_ENDPOINT).strip()
    depth = search_depth or _DEFAULT_DEPTH_ENV or None

    concurrency = (
        3 if (max_variant_concurrency is None and max_page_concurrency is None)
        else max(1, min(v for v in (max_page_concurrency, max_variant_concurrency) if v is not None))
    )

    async def _once(client, query_, per_variant_, t_):
        return await _tavily_once_impl(
            client,
            query_,
            per_variant_,
            t_,
            api_key=key,
            endpoint=ep,
            search_depth=depth,
        )

    return await template_variant_engine(
        q=q,
        limit=max(1, int(limit)),
        per_variant=max(1, int(page_size)),
        fetch_once_fn=_once,    
        gen_variants_fn=_gen_variants,
        engine_name=ENGINE_NAME,
        timeout=timeout,
        max_variant_concurrency=concurrency,
        filter_list=filter_list,
        n_variants=4,
    )
