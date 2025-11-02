import os, httpx
from typing import List, Dict, Optional
from .engine_template import template_paged_engine
from open_webui.retrieval.web.main import SearchResult

ENGINE_NAME = "serper"
DEFAULT_ENDPOINT = os.getenv("SERPER_ENDPOINT", "https://google.serper.dev/search")
DEFAULT_API_KEY  = os.getenv("SERPER_API_KEY") or os.getenv("SERPER_KEY")

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
        raise RuntimeError(f"[{ENGINE_NAME}] SERPER_API_KEY not set")

    page = max(1, int(page))
    num = max(1, min(int(page_size), 10))

    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "OpenWebUI-Search/1.0",
    }
    payload = {
        "q": q,
        "page": page,
        "num": num,
    }

    r = await client.post(endpoint, headers=headers, json=payload, timeout=timeout)

    if r.status_code in (401, 403):
        raise RuntimeError(f"[{ENGINE_NAME}] Unauthorized/Forbidden")
    if r.status_code == 429:
        raise RuntimeError(f"[{ENGINE_NAME}] Rate limited (429)")
    r.raise_for_status()

    data = r.json() or {}
    items = data.get("organic") or []

    try:
        items = sorted(items, key=lambda x: x.get("position", 0))
    except Exception:
        pass
    items = items[:num]

    out: List[Dict] = []
    for it in items:
        url = (it.get("link") or "").strip()
        if not url:
            continue
        out.append({
            "title": it.get("title") or url,
            "url": url,
            "snippet": it.get("description") or "",
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
) -> List[SearchResult]:

    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY)) 

    ep  = (endpoint or DEFAULT_ENDPOINT).strip()
    key = (api_key or DEFAULT_API_KEY or "").strip()

    async def _fetch(client: httpx.AsyncClient, q_: str, page_: int, size_: int, t_: float):
        return await _fetch_page_impl(
            client, q_, page_, size_, t_,
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
