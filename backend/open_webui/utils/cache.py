import os
from urllib.parse import urlparse
from aiocache import caches


def _parse_redis_url(redis_url: str):
    # Expected format: redis://[:password]@host:port/db
    parsed = urlparse(redis_url) if redis_url else None
    if not parsed or parsed.scheme != "redis":
        # Fallback to env host/port
        host = os.environ.get("REDIS_HOST", "localhost")
        port = int(os.environ.get("REDIS_PORT", "6379"))
        db = int(os.environ.get("REDIS_DB", "0"))
        password = os.environ.get("REDIS_PASSWORD")
        return host, port, db, password

    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    db = int((parsed.path or "/0").lstrip("/"))
    password = parsed.password
    return host, port, db, password


host, port, db, password = _parse_redis_url(os.environ.get("REDIS_URL", ""))

caches.set_config(
    {
        "default": {
            "cache": "aiocache.RedisCache",
            "endpoint": host,
            "port": port,
            "password": password,
            "db": db,
            "timeout": 1,
            "serializer": {"class": "aiocache.serializers.StringSerializer"},
        }
    }
)