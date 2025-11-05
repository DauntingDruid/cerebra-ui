from __future__ import annotations

import os
import importlib
import importlib.util
from pathlib import Path

import pytest

try:
    from fastapi import FastAPI, Depends
    from httpx import AsyncClient, ASGITransport
except ImportError:
    FastAPI = None
    AsyncClient = None
    ASGITransport = None

pytestmark = pytest.mark.skipif(
    FastAPI is None or AsyncClient is None,
    reason="fastapi/httpx not installed; skip",
)

API_PATH = "/api/v1/retrieval/process/web/search_links"


def _import_retrieval_module():
    
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

RET = _import_retrieval_module()


class _KV:
    def __init__(self, v): self._v = v
    def get(self): return self._v

def _fake_user():
    class U:
        id = "u"
        name = "Tester"
        email = "t@example.com"
        role = "admin"
    return U()

def _ensure_websearch_config(app, monkeypatch):
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
    _ensure_websearch_config(app, monkeypatch)
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
async def test_search_links_normal_success(monkeypatch):
    
    captured = {}
    async def fake_engine_links(request, engine, q, **kw):
        captured["engine"] = engine
        captured["q"] = q
        captured.update(kw)
        
        print(f"Captured query parameters: {captured}")
        
        return [{"link": "https://a.com/1", "title": "t1"}, {"link": "https://b.com/2", "title": "t2"}]

    monkeypatch.setattr(RET, "_engine_search_links", fake_engine_links)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "q": "opentelemetry overview",
            "limit": 5,
            "page_size": 2,
            "max_page_concurrency": 3,
            "timeout": 7.5,
            "filter_list": [],
            "extra": {},
        }
        
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json=payload)

    print(f"Response status code: {res.status_code}")
    assert res.status_code == 200, res.text

    data = res.json()
    print(f"Response data: {data}")

    assert data["status"] is True
    assert data["engine"] == (os.getenv("WEB_SEARCH_ENGINE") or "google_pse").lower()
    assert data["count"] == 2
    assert isinstance(data["results"], list) and len(data["results"]) == 2

    print(f"Captured query parameters for engine: {captured}")
    assert captured["q"] == "opentelemetry overview"
    assert captured["max_page_concurrency"] == 3
    assert captured["limit"] == 5 and captured["page_size"] == 2 and captured["timeout"] == 7.5

    print("Test passed!")

@pytest.mark.anyio
async def test_search_links_unsupported_engine_fallback_to_default(monkeypatch):
    
    monkeypatch.setattr(RET, "DEFAULT_ENGINE", "google_pse")

    captured = {}
    async def fake_engine_links(request, engine, q, **kw):
        captured["engine"] = engine
        print(f"Captured parameters in fake engine: {captured}")
        return [{"link": "https://x.com"}]

    monkeypatch.setattr(RET, "_engine_search_links", fake_engine_links)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"q": "abc", "engine": "not_exist", "limit": 1, "page_size": 1, "max_page_concurrency": 1}
        
        print(f"Sending payload: {payload}")

        res = await ac.post(API_PATH, json=payload)

    print(f"Response status code: {res.status_code}")
    assert res.status_code == 200, res.text
    data = res.json()

    print(f"Response data: {data}")

    assert data["status"] is True
    assert data["engine"] == "google_pse"
    assert captured["engine"] == "google_pse"
    assert data["count"] == 1 and len(data["results"]) == 1

    print("Test passed!") 


@pytest.mark.anyio
async def test_search_links_concurrency_arg_is_forwarded(monkeypatch):
    
    seen = {}
    async def fake_engine_links(request, engine, q, **kw):
        seen.update(kw)
        print(f"Captured parameters for concurrency: {kw}")
        return []

    monkeypatch.setattr(RET, "_engine_search_links", fake_engine_links)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"q": "abc", "limit": 9, "page_size": 3, "max_page_concurrency": 7}
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json=payload)

    print(f"Response status code: {res.status_code}")
    assert res.status_code == 200, res.text
    assert seen.get("max_page_concurrency") == 7

    print("Test passed!")


@pytest.mark.anyio
async def test_search_links_engine_error_returns_400(monkeypatch):

    async def fake_engine_links(*args, **kwargs):
        raise RuntimeError("engine boom")

    monkeypatch.setattr(RET, "_engine_search_links", fake_engine_links)

    app = _build_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"q": "abc", "limit": 1, "page_size": 1, "max_page_concurrency": 1}
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json=payload)

    assert res.status_code == 400
    print(f"Response status code: {res.status_code}")
    body = res.json()
    print(f"Response body: {body}")
    
    assert "detail" in body
    print("Test passed!")
