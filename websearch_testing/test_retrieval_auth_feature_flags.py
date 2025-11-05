from __future__ import annotations

import importlib, importlib.util
from pathlib import Path
import os

import pytest

try:
    from fastapi import FastAPI, HTTPException
    from httpx import AsyncClient, ASGITransport
except ImportError:
    FastAPI = None
    AsyncClient = None
    ASGITransport = None

pytestmark = pytest.mark.skipif(
    FastAPI is None or AsyncClient is None,
    reason="fastapi/httpx not installed; skip",
)

API_SEARCH = "/api/v1/retrieval/process/web/search"
API_WEB    = "/api/v1/retrieval/process/web"


def _import_retrieval():
    for name in ("backend.open_webui.routers.retrieval", "open_webui.routers.retrieval"):
        try:
            return importlib.import_module(name)
        except Exception:
            pass
    here = Path(__file__).resolve()
    cands = [Path("backend/open_webui/routers/retrieval.py"), Path("open_webui/routers/retrieval.py")]
    cur, seen = here.parent, set()
    while True:
        if cur in seen:
            break
        seen.add(cur)
        for rel in cands:
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

def _ensure_cfg(app, monkeypatch):
    cfg = getattr(app.state, "config", None)
    if cfg is None:
        class _Cfg: ...
        app.state.config = _Cfg(); cfg = app.state.config

    cfg.PLAYWRIGHT_TIMEOUT = getattr(cfg, "PLAYWRIGHT_TIMEOUT", 15000)
    cfg.WEB_SEARCH_CONCURRENT_REQUESTS = getattr(cfg, "WEB_SEARCH_CONCURRENT_REQUESTS", 3)
    cfg.ENABLE_WEB_LOADER_SSL_VERIFICATION = getattr(cfg, "ENABLE_WEB_LOADER_SSL_VERIFICATION", True)
    cfg.WEB_SEARCH_TRUST_ENV = getattr(cfg, "WEB_SEARCH_TRUST_ENV", False)
    cfg.WEB_LOADER_ENGINE = getattr(cfg, "WEB_LOADER_ENGINE", _KV("crawl4ai"))

    cfg.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = getattr(cfg, "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL", True)
    cfg.BYPASS_EMBEDDING_AND_RETRIEVAL = getattr(cfg, "BYPASS_EMBEDDING_AND_RETRIEVAL", True)

def _build_app(monkeypatch, *, override_auth: bool | None = None):
    app = FastAPI()
    _ensure_cfg(app, monkeypatch)
    app.include_router(RET.router, prefix="/api/v1/retrieval")

    try:
        gv = RET.get_verified_user
    except AttributeError:
        from backend.open_webui.utils.auth import get_verified_user as gv

    if override_auth is True:
        class _U:
            id = "u"; name = "Tester"; email = "t@example.com"; role = "admin"
        app.dependency_overrides[gv] = lambda: _U()
    elif override_auth is False:
        
        pass
    else:
        
        class _U:
            id = "u"; name = "Tester"; email = "t@example.com"; role = "admin"
        app.dependency_overrides[gv] = lambda: _U()
    return app


@pytest.fixture
def anyio_backend():
    return "asyncio"



@pytest.mark.anyio
async def test_feature_flag_disabled_blocks_routes(monkeypatch):
    
    monkeypatch.setenv("WS_ENABLE_WEB_SEARCH", "0")
    
    monkeypatch.setenv("WS_REQUIRE_API_KEY", "0")

    app = _build_app(monkeypatch, override_auth=False)

    transport = ASGITransport(app=app)
    dbg = []
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload1 = {"query":"x","limit":1,"page_size":1,"concurrency":1}
        dbg.append(f"Sending payload (SEARCH): {payload1}")
        r1 = await ac.post(API_SEARCH, json={"query":"x","limit":1,"page_size":1,"concurrency":1})
        dbg.append(f"Response status code (SEARCH): {r1.status_code}")
        try:
            dbg.append("[Response data (SEARCH)]\n" + _pretty_json(r1.json()))
        except Exception:
            dbg.append("[Response text (SEARCH)]\n" + r1.text)

        payload2 = {"url":"https://a.com"}
        dbg.append(f"Sending payload (WEB): {payload2}")
        r2 = await ac.post(API_WEB,    json={"url":"https://a.com"})
        dbg.append(f"Response status code (WEB): {r2.status_code}")
        try:
            dbg.append("[Response data (WEB)]\n" + _pretty_json(r2.json()))
        except Exception:
            dbg.append("[Response text (WEB)]\n" + r2.text)

    assert r1.status_code in {403, 404}
    assert r2.status_code in {403, 404}
    
    dbg.append("Test passed!\n")
    print("\n".join(dbg))


@pytest.mark.anyio
async def test_require_api_key_without_token_denied(monkeypatch):

    monkeypatch.setenv("WS_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("WS_REQUIRE_API_KEY", "1")

    app = _build_app(monkeypatch, override_auth=False)

    transport = ASGITransport(app=app)
    dbg = []
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"query":"x","limit":1,"page_size":1,"concurrency":1}
        dbg.append(f"Sending payload: {payload}")
        r = await ac.post(API_SEARCH, json={"query":"x","limit":1,"page_size":1,"concurrency":1})
        dbg.append(f"Response status code: {r.status_code}")
        try:
            dbg.append("[Response data]\n" + _pretty_json(r.json()))
        except Exception:
            dbg.append("[Response text]\n" + r.text)

    assert r.status_code in {401, 403}, r.text

    dbg.append("Test passed!\n")
    print("\n".join(dbg))


@pytest.mark.anyio
async def test_require_api_key_with_verified_user_passes(monkeypatch):
    
    monkeypatch.setenv("WS_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("WS_REQUIRE_API_KEY", "1")

    app = _build_app(monkeypatch, override_auth=True)
    app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = True
    app.state.config.WEB_LOADER_ENGINE = _KV("crawl4ai")

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        return [_Doc("OK"*600, "https://ok.com/page")]
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    transport = ASGITransport(app=app)
    dbg = []
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"url":"https://ok.com/page"}
        dbg.append(f"Sending payload: {payload}")
        r = await ac.post(API_WEB, json={"url":"https://ok.com/page"})
        dbg.append(f"Response status code: {r.status_code}")
        try:
            dbg.append("[Response data]\n" + _pretty_json(r.json()))
        except Exception:
            dbg.append("[Response text]\n" + r.text)

    assert r.status_code == 200, r.text
    data = r.json()
    assert "docs" in data and data["loaded_count"] == 1

    dbg.append("Test passed!\n")
    print("\n".join(dbg))


@pytest.mark.anyio
async def test_search_route_with_verified_user_executes(monkeypatch):
    
    monkeypatch.setenv("WS_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("WS_REQUIRE_API_KEY", "1")

    app = _build_app(monkeypatch, override_auth=True)
    app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = True

    async def fake_search(request, engine, query, **kw):
        return [type("R", (), {"link": "https://a.com/1"})]
    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        return [_Doc("X"*600, "https://a.com/1")]

    monkeypatch.setattr(RET, "search_web_async", fake_search)
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    transport = ASGITransport(app=app)
    dbg = []
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"query":"hello","limit":3,"page_size":1,"concurrency":1}
        dbg.append(f"Sending payload: {payload}")
        r = await ac.post(API_SEARCH, json={"query":"hello","limit":3,"page_size":1,"concurrency":1})
        dbg.append(f"Response status code: {r.status_code}")
        try:
            dbg.append("[Response data]\n" + _pretty_json(r.json()))
        except Exception:
            dbg.append("[Response text]\n" + r.text)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("loaded_count", 0) == 1

    dbg.append("Test passed!\n")
    print("\n".join(dbg))
