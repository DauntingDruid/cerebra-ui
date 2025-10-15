import os, httpx
from typing import List, Dict, Optional
from .engine_template import template_paged_engine
from open_webui.retrieval.web.main import SearchResult

ENGINE_NAME = "serpapi"

_ENV_KEY = os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY")
_ENV_ENGINE = (os.getenv("SERPAPI_ENGINE") or "google").strip().lower()
_ENV_ENDPOINT = os.getenv("SERPAPI_ENDPOINT", "https://serpapi.com/search")

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
        raise RuntimeError("SERPAPI_API_KEY not set")

    page = max(1, int(page))
    page_size = max(1, int(page_size))

    params = {
        "engine": engine,
        "q": q,
        "api_key": api_key,
    }

    if engine == "google":
        params["num"] = min(page_size, 10)
        params["start"] = (page - 1) * params["num"]
    else:
        params["page"] = page

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
        items = sorted(items, key=lambda x: x.get("position", 0))
    except Exception:
        pass

    if engine != "google":
        items = items[:page_size]

    out: List[Dict] = []
    for it in items:
        url = (it.get("link") or "").strip()
        if not url:
            continue
        snippet = it.get("snippet")
        if not snippet:
            words = it.get("snippet_highlighted_words")
            if isinstance(words, list):
                snippet = " ".join(map(str, words))[:300]
            else:
                snippet = ""
        out.append({
            "title": it.get("title") or url,
            "url": url,
            "snippet": snippet,
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
) -> List[SearchResult]:
    
    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY))

    eng = (engine or _ENV_ENGINE or "google").strip().lower()
    ep = (endpoint or _ENV_ENDPOINT).strip()
    key = api_key or _ENV_KEY

    if eng == "google":
        limit = min(int(limit), 100)

    async def _fetch(client, q_, page_, size_, t_):
        return await _fetch_page_impl(
            client, q_, page_, size_, t_,
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
