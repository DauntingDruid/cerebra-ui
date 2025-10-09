import os, asyncio, random, logging, httpx
from typing import List, Optional, Dict
from .engine_template import template_variant_engine, log as core_log
from open_webui.retrieval.web.main import SearchResult

ENGINE_NAME = "bocha"

_ENV_KEY = os.getenv("BOCHA_API_KEY") or os.getenv("BOCHA_KEY")
_ENV_ENDPOINT = (os.getenv("BOCHA_ENDPOINT") or "https://api.bochaai.com/v1/web-search").strip()
_ENV_LANGUAGE = (os.getenv("BOCHA_LANGUAGE") or "en").strip()
_ENV_REGION = (os.getenv("BOCHA_REGION") or "us").strip()
_ENV_MARKET = (os.getenv("BOCHA_MARKET") or "en-US").strip()
_ENV_CC = (os.getenv("BOCHA_CC") or "US").strip()
_ENV_ACCEPT_LANGUAGE = (os.getenv("BOCHA_ACCEPT_LANGUAGE") or "en-US,en;q=0.9").strip()
_ENV_UA = (os.getenv("BOCHA_UA") or "OpenWebUI-Search/1.0").strip()
_ENV_FRESHNESS = (os.getenv("BOCHA_FRESHNESS") or "noLimit").strip() 

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

async def _bocha_once_impl(
    client: httpx.AsyncClient,
    query: str,
    count: int,
    timeout: float,
    *,
    api_key: str,
    endpoint: str,
    language: str,
    region: str,
    market: str,
    cc: str,
    accept_language: str,
    user_agent: str,
    summary: bool,
    freshness: str,
    extra_headers: Optional[Dict] = None,
    extra_payload: Optional[Dict] = None,
    attempt: int = 0,
    max_attempts: int = 3,
) -> List[Dict]:
    if not api_key:
        raise RuntimeError("BOCHA_API_KEY not set")

    url = endpoint
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": accept_language,
        "User-Agent": user_agent,
    }
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v is not None})

    payload = {
        "query": query,
        "summary": bool(summary),
        "freshness": freshness or "noLimit",
        "count": max(1, min(int(count), 10)),
        "language": language,
        "region": region,
        "market": market,
        "cc": cc,
    }
    if extra_payload:
        payload.update({k: v for k, v in extra_payload.items() if v is not None})

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
                    f"[{ENGINE_NAME}] connect error | {method} retry_in={backoff:.1f}s "
                    f"attempt={attempt+1}/{max_attempts-1} err={ex}"
                )
                await asyncio.sleep(backoff)
                return await _bocha_once_impl(
                    client, query, count, timeout,
                    api_key=api_key, endpoint=endpoint,
                    language=language, region=region, market=market, cc=cc,
                    accept_language=accept_language, user_agent=user_agent,
                    summary=summary, freshness=freshness,
                    extra_headers=extra_headers, extra_payload=extra_payload,
                    attempt=attempt+1, max_attempts=max_attempts,
                )
            core_log.warning(f"[{ENGINE_NAME}] connect final fail | {method} err={ex}")
            continue

        if r.status_code in (401, 403):
            core_log.warning(f"[{ENGINE_NAME}] {r.status_code} auth error")
            continue
        if r.status_code == 404:
            core_log.warning(f"[{ENGINE_NAME}] 404 path not found")
            continue
        if r.status_code == 429:
            if attempt + 1 < max_attempts:
                backoff = (1.0 * (2 ** attempt)) + random.uniform(0.2, 0.8)
                core_log.warning(f"[{ENGINE_NAME}] 429 rate limit | retry_in={backoff:.1f}s attempt={attempt+1}/{max_attempts-1}")
                await asyncio.sleep(backoff)
                return await _bocha_once_impl(
                    client, query, count, timeout,
                    api_key=api_key, endpoint=endpoint,
                    language=language, region=region, market=market, cc=cc,
                    accept_language=accept_language, user_agent=user_agent,
                    summary=summary, freshness=freshness,
                    extra_headers=extra_headers, extra_payload=extra_payload,
                    attempt=attempt+1, max_attempts=max_attempts,
                )
            core_log.warning(f"[{ENGINE_NAME}] 429 final fail")
            continue

        try:
            r.raise_for_status()
        except httpx.HTTPStatusError:
            if attempt + 1 < max_attempts:
                backoff = (1.0 * (2 ** attempt)) + random.uniform(0.2, 0.8)
                core_log.warning(
                    f"[{ENGINE_NAME}] {r.status_code} | retry_in={backoff:.1f}s attempt={attempt+1}/{max_attempts-1}"
                )
                await asyncio.sleep(backoff)
                return await _bocha_once_impl(
                    client, query, count, timeout,
                    api_key=api_key, endpoint=endpoint,
                    language=language, region=region, market=market, cc=cc,
                    accept_language=accept_language, user_agent=user_agent,
                    summary=summary, freshness=freshness,
                    extra_headers=extra_headers, extra_payload=extra_payload,
                    attempt=attempt+1, max_attempts=max_attempts,
                )
            core_log.warning(f"[{ENGINE_NAME}] final HTTP fail | status={r.status_code}")
            continue

        data = r.json() or {}
        items = ((data.get("data") or {}).get("webPages") or {}).get("value", []) or []
        out: List[Dict] = []
        for it in items:
            url_i = (it.get("url") or "").strip()
            if not url_i:
                continue
            out.append({
                "title": it.get("name") or url_i,
                "url": url_i,
                "snippet": (it.get("summary") or "") or (it.get("snippet") or ""),
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
    language: Optional[str] = None,
    region: Optional[str] = None,
    market: Optional[str] = None,
    cc: Optional[str] = None,
    accept_language: Optional[str] = None,
    user_agent: Optional[str] = None,
    summary: Optional[bool] = None,
    freshness: Optional[str] = None,
    extra_headers: Optional[Dict] = None,
    extra_payload: Optional[Dict] = None,
) -> List[SearchResult]:
    
    limit = max(1, min(int(limit), MAX_LIMIT)) 
    max_page_concurrency = max(1, min(int(max_page_concurrency), MAX_CONCURRENCY))

    key = api_key or _ENV_KEY
    ep = (endpoint or _ENV_ENDPOINT).strip()
    lang = (language or _ENV_LANGUAGE).strip()
    reg = (region or _ENV_REGION).strip()
    mkt = (market or _ENV_MARKET).strip()
    country = (cc or _ENV_CC).strip()
    acc_lang = (accept_language or _ENV_ACCEPT_LANGUAGE).strip()
    ua = (user_agent or _ENV_UA).strip()
    sum_flag = True if summary is None else bool(summary)
    fresh = (freshness or _ENV_FRESHNESS or "noLimit").strip()

    concurrency = (
        3 if (max_variant_concurrency is None and max_page_concurrency is None)
        else max(1, min(v for v in (max_page_concurrency, max_variant_concurrency) if v is not None))
    )

    async def _fetch_once(client, query, per_variant, to):
        return await _bocha_once_impl(
            client, query, per_variant, to,
            api_key=key, endpoint=ep,
            language=lang, region=reg, market=mkt, cc=country,
            accept_language=acc_lang, user_agent=ua,
            summary=sum_flag, freshness=fresh,
            extra_headers=extra_headers, extra_payload=extra_payload,
        )

    return await template_variant_engine(
        q=q,
        limit=max(1, int(limit)),
        per_variant=max(1, min(int(page_size), 10)),
        fetch_once_fn=_fetch_once,
        gen_variants_fn=_gen_variants,
        engine_name=ENGINE_NAME,
        timeout=timeout,
        max_variant_concurrency=concurrency,
        filter_list=filter_list,
        n_variants=4,
    )
