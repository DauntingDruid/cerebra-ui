import os
import time
from typing import Optional

from open_webui.utils.redis import get_redis_connection, get_sentinels_from_env
from open_webui.env import (
    REDIS_URL,
    REDIS_SENTINEL_HOSTS,
    REDIS_SENTINEL_PORT,
)


_redis_client = None


def _get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = REDIS_URL

    # Fallback to host/port if provided (for local compose setups)
    if not redis_url:
        host = os.environ.get("REDIS_HOST", "localhost")
        port = os.environ.get("REDIS_PORT", "6379")
        redis_url = f"redis://{host}:{port}/0"

    sentinels = get_sentinels_from_env(REDIS_SENTINEL_HOSTS, REDIS_SENTINEL_PORT)
    _redis_client = get_redis_connection(redis_url, sentinels, decode_responses=True)
    return _redis_client


def _session_key(jti: str) -> str:
    return f"open-webui:session:{jti}"


def create_session(jti: str, user_id: str, exp_ts: Optional[int]) -> None:
    if not jti:
        return
    client = _get_redis_client()
    payload = {"user_id": user_id, "issued_at": int(time.time()), "expires_at": exp_ts}
    ttl = None
    if exp_ts:
        ttl = max(1, int(exp_ts - time.time()))
    # If ttl is None, create a key without expiry (not recommended, but allowed for non-expiring JWT)
    if ttl is not None:
        client.set(_session_key(jti), str(payload), ex=ttl)
    else:
        client.set(_session_key(jti), str(payload))


def delete_session(jti: str) -> None:
    if not jti:
        return
    client = _get_redis_client()
    client.delete(_session_key(jti))


def session_exists(jti: str) -> bool:
    if not jti:
        return False
    client = _get_redis_client()
    return client.exists(_session_key(jti)) == 1


def renew_session_ttl(jti: str, exp_ts: Optional[int]) -> None:
    if not jti or not exp_ts:
        return
    client = _get_redis_client()
    ttl = max(1, int(exp_ts - time.time()))
    client.expire(_session_key(jti), ttl)


