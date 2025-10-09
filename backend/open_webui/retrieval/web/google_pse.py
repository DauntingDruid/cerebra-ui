import os, httpx
from typing import List, Dict, Optional
from .engine_template import template_paged_engine

ENGINE_NAME = "google_pse"
DEFAULT_ENDPOINT = os.getenv("GOOGLE_PSE_ENDPOINT", "https://www.googleapis.com/customsearch/v1")

def _env_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_PSE_API_KEY") or os.getenv("GOOGLE_API_KEY")

def _env_cx() -> Optional[str]:
    return os.getenv("GOOGLE_PSE_ENGINE_ID") or os.getenv("GOOGLE_CX")

async def _fetch_page_impl(
    client: httpx.AsyncClient,
    q: str,
    page: int,
    page_size: int,
    timeout: float,
    *,
    api_key: str,
    cx: str,
    endpoint: str,
) -> List[Dict[str, str]]:
    if not api_key:
        raise RuntimeError(f"[{ENGINE_NAME}] GOOGLE_PSE_API_KEY (or GOOGLE_API_KEY) not set")
    if not cx:
        raise RuntimeError(f"[{ENGINE_NAME}] GOOGLE_PSE_ENGINE_ID (or GOOGLE_CX) not set")

    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 10))

    start = 1 + (page - 1) * page_size
    if start > 100:
        return []

    params = {
        "key": api_key,
        "cx": cx,
        "q": q,
        "num": page_size,
        "start": start,
        "fields": "items(title,link,snippet)",
    }

    r = await client.get(endpoint, params=params, timeout=timeout)

    if r.status_code in (401, 403):
        detail = ""
        try:
            detail = (r.json().get("error", {}) or {}).get("message", "")
        except Exception:
            pass
        raise RuntimeError(f"[{ENGINE_NAME}] Unauthorized/Forbidden: {detail or r.reason_phrase}")
    if r.status_code == 429:
        raise RuntimeError(f"[{ENGINE_NAME}] Rate limited (429)")
    r.raise_for_status()

    data = r.json() or {}
    items = data.get("items") or []

    out: List[Dict[str, str]] = []
    for it in items:
        url = (it.get("link") or "").strip()
        if not url:
            continue
        out.append({
            "title": it.get("title") or url,
            "url": url,
            "snippet": it.get("snippet") or "",
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
    engine_id: Optional[str] = None,
    cx: Optional[str] = None,
    endpoint: Optional[str] = None,
):
    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY)) 

    key = (api_key or _env_api_key() or "").strip()
    cx_id = (engine_id or cx or _env_cx() or "").strip()
    ep = (endpoint or DEFAULT_ENDPOINT).strip()

    async def _fetch(client, q_, page_, size_, t_):
        return await _fetch_page_impl(
            client, q_, page_, size_, t_,
            api_key=key, cx=cx_id, endpoint=ep
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
