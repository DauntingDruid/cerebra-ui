from __future__ import annotations

import importlib, importlib.util
from pathlib import Path

import pytest

import json

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

API_PATH = "/api/v1/retrieval/process/web"


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

def _fake_user():
    class U:
        id = "u"; name = "Tester"; email = "t@example.com"; role = "admin"
    return U()

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

    monkeypatch.setenv("WS_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("WS_REQUIRE_API_KEY", "0")

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
async def test_process_web_crawl4ai_returns_docs(monkeypatch):
    app = _build_app(monkeypatch)
    app.state.config.WEB_LOADER_ENGINE = _KV("crawl4ai")
    app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = True

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        assert urls == ["https://a.com/1"]
        return [_Doc("OK"*600, "https://a.com/1")]

    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    transport = ASGITransport(app=app)
    payload = {"url": "https://a.com/1"}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json={"url": "https://a.com/1"})
    
    data = res.json()
    print(f"Response status code: {res.status_code}")
    print("[Response data]\n" + json.dumps(data, ensure_ascii=False, indent=2))

    assert res.status_code == 200, res.text
    
    assert data["status"] is True
    assert "file" not in data
    assert "docs" in data and isinstance(data["docs"], list)
    assert data["loaded_count"] == 1
    assert data["docs"][0]["source"].startswith("https://a.com/1")
    print("Test passed!\n")


@pytest.mark.anyio
async def test_process_web_non_crawl4ai_uses_loader_aload(monkeypatch):
    
    app = _build_app(monkeypatch)
    app.state.config.WEB_LOADER_ENGINE = _KV("requests")
    app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = True

    class _Loader:
        async def aload(self):
            return [_Doc("OK"*700, "https://b.com/page")]

    def fake_get_web_loader(url, verify_ssl, requests_per_second, trust_env=None):
        return _Loader()

    monkeypatch.setattr(RET, "get_web_loader", fake_get_web_loader)

    transport = ASGITransport(app=app)
    payload = {"url": "https://b.com/page"}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json={"url": "https://b.com/page"})
    
    data = res.json()
    print(f"Response status code: {res.status_code}")
    print("[Response data]\n" + json.dumps(data, ensure_ascii=False, indent=2))

    assert res.status_code == 200, res.text
    
    assert data["status"] is True
    assert "file" in data and "data" in data["file"] and "content" in data["file"]["data"]
    assert "docs" not in data and "loaded_count" not in data
    assert data["file"]["meta"]["source"].startswith("https://b.com/page")
    print("Test passed!\n")


@pytest.mark.anyio
async def test_process_web_bypass_off_writes_vector_and_returns_file(monkeypatch):

    app = _build_app(monkeypatch)
    app.state.config.WEB_LOADER_ENGINE = _KV("crawl4ai")
    app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = False
    app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL = False

    async def fake_crawl(request, urls, timeout_sec, concurrency, user_agent):
        return [_Doc("HELLO WORLD", "https://c.com/x")]
    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    called = {"n": 0, "last_docs": None}
    def fake_save_docs_to_vector_db(request, docs, collection_name, overwrite, user):
        called["n"] += 1
        called["last_docs"] = docs

    monkeypatch.setattr(RET, "save_docs_to_vector_db", fake_save_docs_to_vector_db)

    transport = ASGITransport(app=app)
    payload = {"url": "https://c.com/x"}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json={"url": "https://c.com/x"})
    
    data = res.json()
    print(f"Response status code: {res.status_code}")
    print("[Response data]\n" + json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Vector save called: {called['n']} time(s)")
    if called["last_docs"]:
        print(f"Last saved doc source: {called['last_docs'][0].metadata.get('source')}")

    assert res.status_code == 200, res.text
    
    assert "file" in data and "data" in data["file"] and "content" in data["file"]["data"]
    assert "docs" not in data

    assert called["n"] >= 1
    assert isinstance(called["last_docs"], list) and called["last_docs"][0].metadata["source"].endswith("/x")
    print("Test passed!\n")


@pytest.mark.anyio
async def test_process_web_fetch_error_returns_400(monkeypatch):

    app = _build_app(monkeypatch)
    app.state.config.WEB_LOADER_ENGINE = _KV("crawl4ai")
    app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = True

    async def fake_crawl(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(RET, "_crawl4ai_fetch_docs", fake_crawl)

    transport = ASGITransport(app=app)
    payload = {"url": "https://err.com/oops"}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        print(f"Sending payload: {payload}")
        res = await ac.post(API_PATH, json={"url": "https://err.com/oops"})
    print(f"Response status code: {res.status_code}")
    try:
        body = res.json()
        print("[Response data]\n" + json.dumps(body, ensure_ascii=False, indent=2))
    except Exception:
        body = res.text
        print("[Response text]\n" + body)
        
    assert res.status_code == 400
    assert "detail" in body
    print("Test passed!\n")
