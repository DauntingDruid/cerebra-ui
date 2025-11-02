import os, httpx, urllib.parse, json, base64, logging
from typing import List, Dict, Optional, Any, Iterable
from .engine_template import template_paged_engine
from open_webui.retrieval.web.main import SearchResult

log = logging.getLogger(__name__)

ENGINE_NAME = "serply:bing"

DEFAULT_API_KEY     = os.getenv("SERPLY_API_KEY") or os.getenv("SERPLY_KEY")
DEFAULT_ENDPOINT    = os.getenv("SERPLY_BING_ENDPOINT", "https://api.serply.io/v1/b/search")
DEFAULT_HL          = os.getenv("SERPLY_HL", "en")
DEFAULT_GL          = os.getenv("SERPLY_GL", "US")
DEFAULT_UA          = os.getenv("SERPLY_UA", "desktop")
DEFAULT_PROXY       = os.getenv("SERPLY_PROXY", "US")
DEFAULT_MAX_SIZE    = int(os.getenv("SERPLY_MAX_PAGE_SIZE", "20"))
DEFAULT_DEBUG       = (os.getenv("SERPLY_DEBUG", "0") == "1")

def _bing_ck_decode(url: str) -> str:
    try:
        if not url.startswith("https://www.bing.com/ck/a"):
            return url
        qs = urllib.parse.urlparse(url).query
        u = urllib.parse.parse_qs(qs).get("u", [None])[0]
        if not u:
            return url
        if u.startswith("a1"):
            u = u[2:]
        pad = "=" * (-len(u) % 4)
        raw = base64.urlsafe_b64decode((u + pad).encode("utf-8")).decode("utf-8", errors="ignore")
        return urllib.parse.unquote(raw)
    except Exception:
        return url

def _pick_fields(it: Dict[str, Any]) -> Optional[Dict[str, str]]:
    raw = (it.get("link") or it.get("url") or "").strip()
    url = _bing_ck_decode(raw)
    if not url:
        return None
    title = (it.get("title") or it.get("name") or url).strip()
    snippet = (it.get("description") or it.get("snippet") or it.get("summary") or "").strip()
    return {"title": title, "url": url, "snippet": snippet}

def _likely_result_list(obj: Any) -> bool:
    if not isinstance(obj, list) or not obj:
        return False
    keys = {"link", "url", "title", "description", "snippet", "summary"}
    dict_items = [x for x in obj if isinstance(x, dict)]
    if not dict_items:
        return False
    hits = sum(1 for x in dict_items if keys.intersection(x.keys()))
    return hits / len(dict_items) >= 0.5

def _iter_all_lists(o: Any) -> Iterable[list]:
    if isinstance(o, list):
        yield o
        for x in o:
            yield from _iter_all_lists(x)
    elif isinstance(o, dict):
        for v in o.values():
            yield from _iter_all_lists(v)

def _extract_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        for k in ("results", "organic_results", "items"):
            v = data.get(k)
            if isinstance(v, list) and v:
                return v
        for p in ("data", "response", "search", "payload"):
            v = data.get(p)
            if isinstance(v, dict):
                for k in ("results", "organic_results", "items"):
                    lst = v.get(k)
                    if isinstance(lst, list) and lst:
                        return lst
    for lst in _iter_all_lists(data):
        if _likely_result_list(lst):
            return lst
    return []

async def _fetch_page_impl(
    client: httpx.AsyncClient,
    q: str,
    page: int,
    page_size: int,
    timeout: float,
    *,
    api_key: str,
    endpoint: str,
    hl: str,
    gl: str,
    ua: str,
    proxy: str,
    max_page_size: int,
    debug: bool,
) -> List[Dict]:
    if not api_key:
        raise RuntimeError(f"[{ENGINE_NAME}] SERPLY_API_KEY not set")

    page = max(1, int(page))
    num = max(1, min(int(page_size), int(max_page_size)))
    start = (page - 1) * num

    clean_q = (q or "").replace("?", "").replace('"', " ").strip()

    url = f"{endpoint.rstrip('/')}/q={urllib.parse.quote(clean_q, safe='')}"

    mkt = f"{hl}-{gl}"
    params = {
        "q": clean_q,
        "num": num,
        "start": start,
        "language": hl,
        "mkt": mkt,
        "cc": gl,
        "hl": hl,
        "gl": gl,
    }

    headers = {
        "X-Api-Key": api_key,
        "X-User-Agent": ua or "desktop",
        "X-Proxy-Location": proxy or "US",
        "Accept": "application/json",
        "User-Agent": "OpenWebUI-Search/1.0",
    }

    if debug:
        log.debug(f"[{ENGINE_NAME}] GET {url} params={params}")

    r = await client.get(url, params=params, headers=headers, timeout=timeout)

    if r.status_code in (401, 403):
        raise RuntimeError(f"[{ENGINE_NAME}] Unauthorized/Forbidden: {r.text[:200]}")
    if r.status_code == 429:
        raise RuntimeError(f"[{ENGINE_NAME}] Rate limited (429)")
    r.raise_for_status()

    try:
        data = r.json()
    except Exception:
        if debug:
            log.debug(f"[{ENGINE_NAME}] non-JSON head: {r.text[:400]}")
        return []

    if debug:
        try:
            preview = json.dumps(data, ensure_ascii=False)[:500]
            log.debug(f"[{ENGINE_NAME}] preview: {preview}")
        except Exception:
            pass

    if isinstance(data, dict) and "error" in data and not any(
        k in data for k in ("results", "items", "organic_results", "data")
    ):
        return []

    items = _extract_items(data)
    if not items:
        return []

    def _pos(it): return it.get("realPosition") or it.get("position") or it.get("rank") or 0
    try:
        items = sorted(items, key=_pos)
    except Exception:
        pass
    items = items[:num]

    out: List[Dict] = []
    for it in items:
        picked = _pick_fields(it)
        if not picked:
            continue
        out.append({
            "title": picked["title"],
            "url": picked["url"],
            "link": picked["url"],
            "snippet": picked["snippet"],
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
    hl: Optional[str] = None,                 
    gl: Optional[str] = None,               
    ua: Optional[str] = None,                
    proxy: Optional[str] = None,             
    max_page_size: Optional[int] = None,      
    debug: Optional[bool] = None,       
) -> List[SearchResult]:

    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY)) 

    key   = (api_key or DEFAULT_API_KEY or "").strip()
    ep    = (endpoint or DEFAULT_ENDPOINT).strip()
    _hl   = (hl or DEFAULT_HL).strip()
    _gl   = (gl or DEFAULT_GL).strip()
    _ua   = (ua or DEFAULT_UA).strip()
    _proxy = (proxy or DEFAULT_PROXY).strip()
    _mps  = int(max_page_size if max_page_size is not None else DEFAULT_MAX_SIZE)
    _dbg  = bool(DEFAULT_DEBUG if debug is None else debug)

    async def _fetch(client: httpx.AsyncClient, q_: str, page_: int, size_: int, t_: float):
        return await _fetch_page_impl(
            client, q_, page_, size_, t_,
            api_key=key,
            endpoint=ep,
            hl=_hl,
            gl=_gl,
            ua=_ua,
            proxy=_proxy,
            max_page_size=_mps,
            debug=_dbg,
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
