from __future__ import annotations

import importlib, importlib.util
from pathlib import Path
import os

import pytest

try:
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
except ImportError:
    FastAPI = None
    AsyncClient = None
    ASGITransport = None

pytestmark = pytest.mark.skipif(
    FastAPI is None or AsyncClient is None,
    reason="fastapi/httpx not installed; skip",
)

API_PATH = "/api/v1/retrieval/process/web/search"


def _import_retrieval():
    for name in ("backend.open_webui.routers.retrieval", "open_webui.routers.retrieval"):
        try:
            return importlib.import_module(name)
        except Exception:
            pass

    here = Path(__file__).resolve()
    candidates = [
        Path("backend/open_webui/routers/retrieval.py"),
        Path("open_webui/routers/retrieval.py"),
    ]
    cur = here.parent
    seen = set()
    while True:
        if cur in seen:
            break
        seen.add(cur)
        for rel in candidates:
            p = cur / rel
            if p.exists():
                spec = importlib.util.spec_from_file_location("RET_MOD", p)
                mod = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(mod)
                return mod
        if cur.parent == cur:
            break
        cur = cur.parent
    raise ModuleNotFoundError("cannot import retrieval module")

RET = _import_retrieval()


class _KV:
    def __init__(self, v): self._v = v
    def get(self): return self._v

class _Doc:
    def __init__(self, content: str, src: str, title="t"):
        self.page_content = content
        self.metadata = {"source": src, "title": title, "loader": "crawl4ai", "structured": False}

def _fake_user():
    class U:
        id = "u"
        name = "Tester"
        email = "t@example.com"
        role = "admin"
    return U()

def _ensure_cfg(app, monkeypatch):
    cfg = getattr(app.state, "config", None)
    if cfg is None:
        class _Cfg: ...
        app.state.config = _Cfg()
        cfg = app.state.config

    if not hasattr(cfg, "WEB_SEARCH_DOMAIN_FILTER_LIST"):
        cfg.WEB_SEARCH_DOMAIN_FILTER_LIST = []
    if not hasattr(cfg, "PLAYWRIGHT_TIMEOUT"):
        cfg.PLAYWRIGHT_TIMEOUT = 15000
    if not hasattr(cfg, "WEB_SEARCH_CONCURRENT_REQUESTS"):
        cfg.WEB_SEARCH_CONCURRENT_REQUESTS = 3
    if not hasattr(cfg, "ENABLE_WEB_LOADER_SSL_VERIFICATION"):
        cfg.ENABLE_WEB_LOADER_SSL_VERIFICATION = True
    if not hasattr(cfg, "WEB_FETCH_TOP_K"):
        cfg.WEB_FETCH_TOP_K = 15

    if not hasattr(cfg, "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL"):
        cfg.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = True
    if not hasattr(cfg, "BYPASS_EMBEDDING_AND_RETRIEVAL"):
        cfg.BYPASS_EMBEDDING_AND_RETRIEVAL = True

    if not hasattr(cfg, "WEB_LOADER_ENGINE"):
        cfg.WEB_LOADER_ENGINE = _KV("crawl4ai")
    if not hasattr(cfg, "WEB_SEARCH_ENGINE"):
        cfg.WEB_SEARCH_ENGINE = _KV("google_pse")

    if not hasattr(cfg, "ENABLE_WEB_INLINE_EMBED_FILTER"):
        cfg.ENABLE_WEB_INLINE_EMBED_FILTER = False
    if not hasattr(cfg, "ENABLE_WEB_INLINE_RERANK"):
        cfg.ENABLE_WEB_INLINE_RERANK = False
    if not hasattr(cfg, "TIKTOKEN_ENCODING_NAME"):
        cfg.TIKTOKEN_ENCODING_NAME = None
    if not hasattr(cfg, "WEB_INLINE_VECTOR_TOPK"):
        cfg.WEB_INLINE_VECTOR_TOPK = 30
    if not hasattr(cfg, "WEB_INLINE_RERANK_TOPN"):
        cfg.WEB_INLINE_RERANK_TOPN = 10
    if not hasattr(cfg, "WEB_SEARCH_TRUST_ENV"):
        cfg.WEB_SEARCH_TRUST_ENV = False

    monkeypatch.setenv("WS_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("WS_REQUIRE_API_KEY", "0")
    monkeypatch.setenv("WEB_SEARCH_ENGINE", "google_pse")


def _build_app(monkeypatch):
    app = FastAPI()
    _ensure_cfg(app, monkeypatch)
    app.include_router(RET.router, prefix="/api/v1/retrieval")
    try:
        gv = RET.get_verified_user
    except AttributeError:
        from backend.open_webui.utils.auth import get_verified_user as gv
    app.dependency_overrides[gv] = _fake_user
    return app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_r1_success_returns_docs(monkeypatch):

    async def fake_search(request, engine, query, **kw):
        return [type("R", (), {"link": "https://a.com/1"})]

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        assert urls == ["https://a.com/1"]
        return [_Doc("X"*600, "https://a.com/1")]

    monkeypatch.setattr(RET, "search_web_async", fake_search)
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"query": "q", "limit": 5, "page_size": 2, "concurrency": 2}
        res = await ac.post(API_PATH, json=payload)

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["loaded_count"] == 1
    assert data.get("docs") and data["docs"][0]["metadata"]["source"].startswith("https://a.com/1")

    print(f"Test R1 Success - Query Sent: {payload['query']}, Response Status: {res.status_code}")
    print(f"Loaded Count: {data['loaded_count']}")
    print(f"First Document Source: {data['docs'][0]['metadata']['source']}")
    print(f"Complete Response Data: {data}")
    print(f"Response Time: {res.elapsed.total_seconds()} seconds")
    print("Test passed!\n")

@pytest.mark.anyio
async def test_r1_short_then_r2_new_only_success(monkeypatch):
    calls = {"n": 0, "queries": []}

    async def fake_search(request, engine, query, **kw):
        calls["n"] += 1
        calls["queries"].append(query)
        if calls["n"] == 1:
            return [type("R", (), {"link": "https://a.com/1?utm_source=ad"})]
        return [
            type("R", (), {"link": "https://b.com/2"}),
            type("R", (), {"link": "https://a.com/1"}),
        ]

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        out = []
        for u in urls:
            if "a.com/1" in u:
                out.append(_Doc("too short", u))
            elif "b.com/2" in u:
                out.append(_Doc("OK"*600, u))
        return out

    monkeypatch.setattr(RET, "search_web_async", fake_search)
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"query": "q", "limit": 5, "page_size": 2, "concurrency": 2}
        res = await ac.post(API_PATH, json=payload)

    assert res.status_code == 200, res.text
    data = res.json()
    assert data["loaded_count"] == 1
    assert data["docs"][0]["metadata"]["source"].startswith("https://b.com/2")

    assert len(calls["queries"]) >= 2

    print(f"Test R1 Short Then R2 Success - Query Sent: {payload['query']}, Response Status: {res.status_code}")
    print(f"Loaded Count: {data['loaded_count']}")
    print(f"First Document Source: {data['docs'][0]['metadata']['source']}")
    print(f"Complete Response Data: {data}")
    print(f"Response Time: {res.elapsed.total_seconds()} seconds")
    print("Test passed!\n")


@pytest.mark.anyio
async def test_r1_short_then_r2_no_new_links_returns_empty(monkeypatch):
    async def fake_search(request, engine, query, **kw):
        return [type("R", (), {"link": "https://a.com/1#gclid=123"})]

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        return [_Doc("short", urls[0])]

    monkeypatch.setattr(RET, "search_web_async", fake_search)
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"query": "q", "limit": 5, "page_size": 2, "concurrency": 2}
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json={"query": "q", "limit": 5, "page_size": 2, "concurrency": 2})

    print(f"Response status code: {res.status_code}")
    data = res.json()
    print(f"Response data: {data}")

    assert res.status_code == 200, res.text
    assert data.get("docs", []) == []
    assert data["loaded_count"] == 0
    print("Test passed!\n")


@pytest.mark.anyio
async def test_antibot_exception_then_r2_success(monkeypatch):
    
    calls = {"n": 0}

    async def fake_search(request, engine, query, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return [type("R", (), {"link": "https://anti.example.com/p"})]
        return [
            type("R", (), {"link": "https://ok.com/page"}),
            type("R", (), {"link": "https://anti.example.com/p"}),
        ]

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        out = []
        for u in urls:
            if "anti.example.com" in u:
                raise RuntimeError("anti-bot")
            elif "ok.com/page" in u:
                out.append(_Doc("OK"*600, u))
        return out

    monkeypatch.setattr(RET, "search_web_async", fake_search)
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"query": "antibot", "limit": 5, "page_size": 2, "concurrency": 2}
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json={"query": "antibot", "limit": 5, "page_size": 2, "concurrency": 2})

    print(f"Response status code: {res.status_code}")
    data = res.json()
    print(f"Response data: {data}")
    assert res.status_code == 200, res.text
    assert data["loaded_count"] == 1
    assert data["docs"][0]["metadata"]["source"].startswith("https://ok.com/page")
    print("Test passed!\n")


@pytest.mark.anyio
async def test_js_heavy_r1_too_short_then_r2_success(monkeypatch):
    async def fake_search(request, engine, query, **kw):
        if query == "js-heavy":
            return [type("R", (), {"link": "https://js.example.com/spa"})]
        return [type("R", (), {"link": "https://ok.com/page"})]

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        out = []
        for u in urls:
            if "js.example.com/spa" in u:
                out.append(_Doc("x"*50, u))
            elif "ok.com/page" in u:
                out.append(_Doc("OK"*600, u))
        return out

    monkeypatch.setattr(RET, "search_web_async", fake_search)
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"query": "js-heavy", "limit": 5, "page_size": 2, "concurrency": 2}
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json={"query": "js-heavy", "limit": 5, "page_size": 2, "concurrency": 2})

    print(f"Response status code: {res.status_code}")
    data = res.json()
    print(f"Response data: {data}")

    assert res.status_code == 200, res.text
    assert data["loaded_count"] == 1
    assert data["docs"][0]["metadata"]["source"].startswith("https://ok.com/page")
    print("Test passed!\n")

@pytest.mark.anyio
async def test_pdf_bias_r2_appends_negative_pdf(monkeypatch):
    
    seen_queries = []

    async def fake_search(request, engine, query, **kw):
        seen_queries.append(query)
        
        if len(seen_queries) == 1:
            return [type("R", (), {"link": "https://pdf-heavy.org/p1.pdf"})]
        
        return [type("R", (), {"link": "https://plain.org/readme"})]

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        out = []
        for u in urls:
            if u.endswith(".pdf"):
                
                out.append(_Doc("short", u))
            else:
                out.append(_Doc("OK"*600, u))
        return out

    monkeypatch.setattr(RET, "search_web_async", fake_search)
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"query": "OpenTelemetry filetype:pdf", "limit": 5, "page_size": 2, "concurrency": 2}
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json={"query": "OpenTelemetry filetype:pdf", "limit": 5, "page_size": 2, "concurrency": 2})

    print(f"Response status code: {res.status_code}")
    data = res.json()
    print(f"Response data: {data}")
    print(f"Captured queries for R2: {seen_queries}")

    assert res.status_code == 200, res.text
    
    assert data["loaded_count"] == 1
    
    assert any("-filetype:pdf" in q.lower() for q in seen_queries[1:]), f"queries captured: {seen_queries}"
    print("Test passed!\n")
