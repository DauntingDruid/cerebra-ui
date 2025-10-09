import json
from typing import Optional


def _get_redis(app) -> Optional[object]:
    try:
        return getattr(app.state.config, "_redis", None)
    except Exception:
        return None


def _chat_key(chat_id: str) -> str:
    return f"open-webui:chat-cache:item:{chat_id}"


def _recent_key(user_id: str) -> str:
    return f"open-webui:chat-cache:recent:{user_id}"


def get_cached_chat(app, chat_id: str) -> Optional[dict]:
    r = _get_redis(app)
    if not r or not app.state.config.ENABLE_CHAT_CACHE:
        return None
    data = r.get(_chat_key(chat_id))
    if not data:
        return None
    try:
        return json.loads(data)
    except Exception:
        return None


def set_cached_chat(app, chat_id: str, chat_response: dict) -> None:
    r = _get_redis(app)
    if not r or not app.state.config.ENABLE_CHAT_CACHE:
        return
    ttl = int(app.state.config.CHAT_CACHE_TTL_SECONDS)
    r.setex(_chat_key(chat_id), ttl, json.dumps(chat_response))


def delete_chat_cache(app, chat_id: str) -> None:
    r = _get_redis(app)
    if not r:
        return
    try:
        r.delete(_chat_key(chat_id))
    except Exception:
        pass


def touch_recent(app, user_id: str, chat_id: str) -> None:
    """Maintain a small LRU list of recent cached chats per user and evict overflow."""
    r = _get_redis(app)
    if not r or not app.state.config.ENABLE_CHAT_CACHE:
        return
    key = _recent_key(user_id)
    try:
        # Remove existing occurrence
        r.lrem(key, 0, chat_id)
        # Push to head
        r.lpush(key, chat_id)
        # Trim and evict extra
        max_recent = int(app.state.config.CHAT_CACHE_MAX_RECENT)
        length = r.llen(key)
        while length and length > max_recent:
            evicted = r.rpop(key)
            if evicted:
                r.delete(_chat_key(evicted))
            length = r.llen(key)
        # Set a TTL on the list so it garbage-collects eventually
        r.expire(key, int(app.state.config.CHAT_CACHE_TTL_SECONDS))
    except Exception:
        pass


