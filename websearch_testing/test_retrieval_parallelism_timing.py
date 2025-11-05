from __future__ import annotations

import time
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

API_SEARCH = "/api/v1/retrieval/process/web/search"


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
    def __init__(self, content: str, src: str):
        self.page_content = content
        self.metadata = {"source": src, "title": "t", "loader": "crawl4ai", "structured": False}

def _fake_user():
    class U:
        id = "u"; name = "Tester"; email = "t@example.com"; role = "admin"
    return U()

def _build_app(monkeypatch):
    app = FastAPI()
    class _Cfg: ...
    app.state.config = _Cfg()
    cfg = app.state.config
    cfg.WEB_LOADER_ENGINE = _KV("crawl4ai")
    cfg.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = True
    cfg.BYPASS_EMBEDDING_AND_RETRIEVAL = True
    cfg.PLAYWRIGHT_TIMEOUT = 15000
    cfg.WEB_SEARCH_CONCURRENT_REQUESTS = 3
    cfg.ENABLE_WEB_LOADER_SSL_VERIFICATION = True
    cfg.WEB_SEARCH_TRUST_ENV = False

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
async def test_parallelism_walltime_speedup(monkeypatch):
    
    app = _build_app(monkeypatch)

    class _R:
        def __init__(self, link): self.link = link

    N = 9 
    S = 0.25 
    LINKS = [f"https://p{i}.example.com/item/{i}" for i in range(N)]

    async def fake_search(request, engine, query, limit=None, page_size=None, max_conc=None, run_id=None):

        return [_R(u) for u in LINKS]

    monkeypatch.setattr(RET, "search_web_async", fake_search)

    import asyncio
    async def fake_fetch_one(request, url, timeout_s, user_agent, verify_ssl, rps, trust_env):
        await asyncio.sleep(S)
        return _Doc("OK"*600, url)

    monkeypatch.setattr(RET, "_fetch_one_with_crawl4ai_fallback", fake_fetch_one)

    dbg = []

    async def _run(concurrency: int):
        transport = ASGITransport(app=app)
        payload = {"query": "parallel-proof", "limit": N, "page_size": N, "concurrency": concurrency}
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            dbg.append(f"Sending payload (conc={concurrency}): {payload}")
            t0 = time.perf_counter()
            res = await ac.post(
                API_SEARCH,
                json={"query": "parallel-proof", "limit": N, "page_size": N, "concurrency": concurrency},
            )
            dt = time.perf_counter() - t0
            dbg.append(f"Response status code (conc={concurrency}): {res.status_code}")
            try:
                body = res.json()
                
                mini = {
                    "status": body.get("status"),
                    "loaded_count": body.get("loaded_count"),
                    "filenames": body.get("filenames", None),
                    
                    "doc_sources_sample": [
                        (body.get("docs") or [{}])[0].get("metadata", {}).get("source") if body.get("docs") else None,
                        (body.get("docs") or [{}])[-1].get("metadata", {}).get("source") if body.get("docs") else None,
                    ],
                }
                dbg.append(f"[Response data (conc={concurrency})]\n" + json.dumps(mini, ensure_ascii=False, indent=2))
            except Exception:
                txt = res.text
                if len(txt) > 200:
                    txt = txt[:200] + "...(truncated)"
                dbg.append(f"[Response text (conc={concurrency})]\n{res.text}")

        assert res.status_code == 200, res.text
        body = res.json()
        
        assert body.get("loaded_count") == N
        assert "docs" in body and len(body["docs"]) == N
        dbg.append(f"[Elapsed] conc={concurrency} -> {dt:.3f}s")
        return dt

    t_seq = await _run(concurrency=1)
    t_par = await _run(concurrency=3)

    speedup = t_seq / max(t_par, 1e-9)
    dbg.append(f"[parallelism] N={N} S={S}s  t_seq={t_seq:.3f}s  t_par={t_par:.3f}s  speedup={speedup:.2f}x")

    assert speedup >= 2.0

    dbg.append("Test passed!\n")
    print("\n".join(dbg))
