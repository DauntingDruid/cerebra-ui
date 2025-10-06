import os
import sys
import asyncio
import time
from datetime import timedelta
import pytest

# Ensure "backend" is on sys.path so we can import open_webui.* directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_module():
    # Force aiocache to use in-memory cache for tests (no Redis required)
    from aiocache import caches

    caches.set_config(
        {
            "default": {
                "cache": "aiocache.SimpleMemoryCache",
                "serializer": {"class": "aiocache.serializers.StringSerializer"},
            }
        }
    )

def test_jwt_has_jti():
    from open_webui.utils.auth import create_token, decode_token

    # No expiry
    t1 = create_token({"id": "user-1"})
    d1 = decode_token(t1)
    assert d1 is not None and d1.get("jti")

    # With expiry
    t2 = create_token({"id": "user-2"}, expires_delta=timedelta(seconds=30))
    d2 = decode_token(t2)
    assert d2 is not None and d2.get("jti") and d2.get("exp")

# Check if Redis is available
def _redis_available():
    import socket

    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
def test_session_store_lifecycle():
    from open_webui.utils.sessions import create_session, session_exists, delete_session

    jti = "test-jti-123"
    user_id = "user-xyz"
    exp = int(time.time()) + 30

    # Create
    create_session(jti, user_id, exp)
    assert session_exists(jti)

    # Delete
    delete_session(jti)
    assert not session_exists(jti)

@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
def test_session_renew_ttl():
    # Verify sliding TTL logic increases TTL when renewed with a farther exp
    import open_webui.utils.sessions as sessions

    jti = "test-jti-ttl"
    user_id = "user-abc"
    now = int(time.time())

    exp_initial = now + 5
    sessions.create_session(jti, user_id, exp_initial)

    client = sessions._get_redis_client()
    key = sessions._session_key(jti)
    ttl1 = client.ttl(key)
    assert ttl1 > 0

    # Renew to a much larger exp so TTL should increase
    exp_renewed = int(time.time()) + 30
    sessions.renew_session_ttl(jti, exp_renewed)
    ttl2 = client.ttl(key)

    # Allow small delays; ensure ttl increased by at least a few seconds
    assert ttl2 > ttl1

    sessions.delete_session(jti)
    assert client.exists(key) == 0











# def test_fast_chat_cache_roundtrip(monkeypatch):
#     import open_webui.routers.chats as chats_router
#     from open_webui.models.chats import ChatTitleIdResponse

#     async def runner():
#         calls = {"count": 0}

#         def fake_get_chat_title_id_list_by_user_id(user_id: str, limit=None, **kwargs):
#             calls["count"] += 1
#             items = [
#                 ChatTitleIdResponse(id=f"c{i}", title=f"Chat {i}", updated_at=i, created_at=i)
#                 for i in range(1, 6)
#             ]
#             return items[: limit or 3]

#         monkeypatch.setattr(
#             chats_router.Chats, "get_chat_title_id_list_by_user_id", fake_get_chat_title_id_list_by_user_id
#         )

#         user_id = "user-1"

#         # First call: miss -> populate
#         items1 = await chats_router._get_fast_chats(user_id, 3)
#         assert len(items1) == 3
#         assert calls["count"] == 1

#         # Second call: hit -> no DB call
#         items2 = await chats_router._get_fast_chats(user_id, 3)
#         assert len(items2) == 3
#         assert calls["count"] == 1

#         # Invalidate
#         await chats_router._invalidate_fast_cache(user_id, counts=[3])
#         items3 = await chats_router._get_fast_chats(user_id, 3)
#         assert len(items3) == 3
#         assert calls["count"] == 2

#     asyncio.run(runner())