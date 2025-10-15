import os
from typing import List, Dict, Optional
import httpx
from .engine_template import template_paged_engine

ENGINE_NAME = "searchapi"
DEFAULT_ENDPOINT = os.getenv("SEARCHAPI_ENDPOINT", "https://www.searchapi.io/api/v1/search")
ALLOWED_ENGINES = {"google", "bing", "brave", "duckduckgo"}


def _normalize_engine(engine: Optional[str]) -> str:
    e = (engine or os.getenv("SEARCHAPI_ENGINE") or "google").strip().lower()
    return e if e in ALLOWED_ENGINES else "google"


async def _fetch_page_impl(
    client: httpx.AsyncClient,
    q: str,
    page: int,
    page_size: int,
    timeout: float,
    *,
    api_key: str,
    engine: str,
    endpoint: str,
) -> List[Dict]:
    if not api_key:
        raise RuntimeError(f"[{ENGINE_NAME}] SEARCHAPI_API_KEY not set")

    page = max(1, int(page))
    page_size = max(1, int(page_size))

    params = {
        "engine": engine,
        "q": q,
        "api_key": api_key,
        "page": page,
    }
    if engine == "google":
        params["num"] = min(page_size, 10)

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
    items = (data.get("organic_results") or [])

    try:
        items.sort(key=lambda x: x.get("position", 0))
    except Exception:
        pass

    items = items[:page_size]

    out: List[Dict] = []
    for it in items:
        url = (it.get("link") or "").strip()
        if not url:
            continue
        out.append({
            "title": it.get("title") or url,
            "url": url,
            "snippet": it.get("snippet") or it.get("description") or "",
            "source": f"{ENGINE_NAME}:{engine}",
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
    engine: Optional[str] = None,
    endpoint: Optional[str] = None,
):
    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY)) 

    eng = _normalize_engine(engine)
    ep = (endpoint or DEFAULT_ENDPOINT).strip()
    key = api_key or os.getenv("SEARCHAPI_API_KEY")

    if eng == "google":
        limit = min(int(limit), 100)

    async def _fetch(client, q_, page, size, t):
        return await _fetch_page_impl(
            client, q_, page, size, t,
            api_key=key, engine=eng, endpoint=ep
        )

    return await template_paged_engine(
        q=q,
        limit=limit,
        page_size=page_size,
        fetch_page_fn=_fetch,                    
        engine_name=f"{ENGINE_NAME}:{eng}",
        timeout=timeout,
        max_page_concurrency=max_page_concurrency, 
        filter_list=filter_list,
    )
