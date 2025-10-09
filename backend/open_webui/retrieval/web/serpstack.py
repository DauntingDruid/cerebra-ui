import os, httpx
from typing import List, Dict, Optional
from .engine_template import template_paged_engine
from open_webui.retrieval.web.main import SearchResult

ENGINE_NAME = "serpstack"

_SERPSTACK_KEY_ENV = os.getenv("SERPSTACK_API_KEY")
_DEFAULT_ENDPOINT_HTTPS = os.getenv("SERPSTACK_ENDPOINT_HTTPS", "https://api.serpstack.com/search")
_DEFAULT_ENDPOINT_HTTP  = os.getenv("SERPSTACK_ENDPOINT_HTTP",  "http://api.serpstack.com/search")
_SERPSTACK_HTTPS_ENV = os.getenv("SERPSTACK_HTTPS")

def _truthy(v: Optional[str]) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "on"}

async def _fetch_page_impl(
    client: httpx.AsyncClient,
    q: str,
    page: int,
    page_size: int,
    timeout: float,
    *,
    api_key: str,
    endpoint: str,
) -> List[Dict]:
    if not api_key:
        raise RuntimeError("SERPSTACK_API_KEY not set")

    page = max(1, int(page))
    num = max(1, min(int(page_size), 10)) 

    params = {
        "access_key": api_key,
        "query": q,
        "page": page,
        "num": num,
        "output": "json",
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "OpenWebUI-Search/1.0",
    }

    r = await client.get(endpoint, params=params, headers=headers, timeout=timeout)

    if r.status_code in (401, 403):
        raise RuntimeError(f"[{ENGINE_NAME}] Unauthorized/Forbidden")
    if r.status_code == 429:
        raise RuntimeError(f"[{ENGINE_NAME}] Rate limited (429)")
    r.raise_for_status()

    data = r.json() or {}
    items = data.get("organic_results") or []

    try:
        items = sorted(items, key=lambda x: x.get("position", 0))
    except Exception:
        pass
    items = items[:num]

    out: List[Dict] = []
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        out.append({
            "title": it.get("title") or url,
            "url": url,
            "snippet": it.get("snippet") or it.get("description") or "",
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
    filter_list: Optional[List[str]] = None,
    *,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    https_enabled: Optional[bool] = None,
) -> List[SearchResult]:
    
    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY)) 

    key = api_key or _SERPSTACK_KEY_ENV
    use_https = https_enabled if https_enabled is not None else _truthy(_SERPSTACK_HTTPS_ENV)
    ep = (endpoint or (_DEFAULT_ENDPOINT_HTTPS if use_https else _DEFAULT_ENDPOINT_HTTP)).strip()

    limit = max(1, min(int(limit), 100))

    async def _fetch(client, q_, page, size, t):
        return await _fetch_page_impl(
            client, q_, page, size, t,
            api_key=key,
            endpoint=ep,
        )

    return await template_paged_engine(
        q=q,
        limit=limit,
        page_size=page_size,
        fetch_page_fn=_fetch,
        engine_name=ENGINE_NAME,
        timeout=timeout,
        max_page_concurrency=max_page_concurrency,
        filter_list=filter_list,
    )
