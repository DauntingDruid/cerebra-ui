"""
Redis-backed chat cache helpers.

This module exposes small, focused helpers used by the chats router and
streaming middleware to cache an already-hydrated ChatResponse in Redis
and maintain a short per-user LRU list of recently opened chats.

We cache and return the full ChatResponse snapshot for 
that chat, including the chat JSON with its history.

Design constraints:
- Cache is an optimization only. The database remains the source of truth.
- Cache entries are JSON-serialized ChatResponse snapshots under:
    open-webui:chat-cache:item:{chat_id}
- A short, per-user LRU (head=most recent) is tracked under:
    open-webui:chat-cache:recent:{user_id}
- TTL applies to both the item and the recent list key to garbage-collect
  stale entries in low-traffic environments.

Runtime configuration is read from FastAPI app state (AppConfig):
- ENABLE_CHAT_CACHE (bool)
- CHAT_CACHE_TTL_SECONDS (int)
- CHAT_CACHE_MAX_RECENT (int)

Failures (e.g., Redis unavailable) are ignored on purpose to keep the
request path resilient.
"""

import json
from typing import Optional


def _get_redis(app) -> Optional[object]:
    """Return a redis client from app.state.config or None if unavailable.

    We rely on AppConfig wiring to have established a decode_responses=True
    connection, so values are plain str and JSON can be safely parsed.
    """
    try:
        return getattr(app.state.config, "_redis", None)
    except Exception:
        return None


def _chat_key(chat_id: str) -> str:
    """Per-chat snapshot key: contains serialized ChatResponse JSON."""
    return f"open-webui:chat-cache:item:{chat_id}"


def _recent_key(user_id: str) -> str:
    """Per-user list key: LRU of recently opened chats (head is most recent)."""
    return f"open-webui:chat-cache:recent:{user_id}"


def get_cached_chat(app, chat_id: str) -> Optional[dict]:
    """Fetch a cached ChatResponse snapshot for chat_id.

    Returns:
        A dict compatible with ChatResponse(**snapshot), or None if
        caching is disabled, missing, or deserialization fails.
    """
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
    """Store a ChatResponse snapshot for chat_id with TTL."""
    r = _get_redis(app)
    if not r or not app.state.config.ENABLE_CHAT_CACHE:
        return
    ttl = int(app.state.config.CHAT_CACHE_TTL_SECONDS)
    r.setex(_chat_key(chat_id), ttl, json.dumps(chat_response))


def delete_chat_cache(app, chat_id: str) -> None:
    """Invalidate a single chat cache entry (no-op on failure)."""
    r = _get_redis(app)
    if not r:
        return
    try:
        r.delete(_chat_key(chat_id))
    except Exception:
        pass


def touch_recent(app, user_id: str, chat_id: str) -> None:
    """Update per-user LRU of recently opened chats and enforce size/TTL.

    Strategy:
    - Remove any duplicate of chat_id within the list
    - Push chat_id to the head (most recent)
    - Trim to max_recent by popping from tail; delete evicted item snapshot
    - Refresh TTL on the list key to allow GC when inactive
    """
    r = _get_redis(app)
    if not r or not app.state.config.ENABLE_CHAT_CACHE:
        return
    key = _recent_key(user_id)
    try:
        ttl = int(app.state.config.CHAT_CACHE_TTL_SECONDS)
        max_recent = int(app.state.config.CHAT_CACHE_MAX_RECENT)

        # 1) Remove duplicate and push to head in a single pipeline round-trip
        p = r.pipeline()
        p.lrem(key, 0, chat_id)
        p.lpush(key, chat_id)
        p.expire(key, ttl)
        p.execute()

        # 2) Fetch overflow tail beyond max_recent (0-based indexing)
        tail = r.lrange(key, max_recent, -1)
        if tail:
            # 3) Trim list and delete evicted snapshots in one batch
            p2 = r.pipeline()
            p2.ltrim(key, 0, max_recent - 1)
            for evicted in tail:
                p2.delete(_chat_key(evicted))
            p2.execute()
    except Exception:
        pass



def remove_from_recent(app, user_id: str, chat_id: str) -> None:
    """Remove chat_id from the user's recent LRU list (no-op on failure).

    This does not delete the snapshot item key; pair with delete_chat_cache
    when the chat itself is deleted.
    """
    r = _get_redis(app)
    if not r or not app.state.config.ENABLE_CHAT_CACHE:
        return
    key = _recent_key(user_id)
    try:
        r.lrem(key, 0, chat_id)
    except Exception:
        pass


def clear_recent_for_user(app, user_id: str) -> None:
    """Clear the entire recent LRU list for a user (no-op on failure)."""
    r = _get_redis(app)
    if not r or not app.state.config.ENABLE_CHAT_CACHE:
        return
    key = _recent_key(user_id)
    try:
        r.delete(key)
    except Exception:
        pass

