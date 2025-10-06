# Redis Setup for CerebraUI

This guide covers enabling Redis-backed sessions and the fast chat cache.

## 1) Prerequisites

- Redis 6+ reachable from the backend
- URL form: `redis://[:password]@host:port/db`
- Optional: Redis Sentinel (see below)

## 2) Environment

Set at least the following in your `.env`:

```
# Core
REDIS_URL=redis://localhost:6379/0
ENABLE_REDIS_SESSIONS=True

# Optional (fallbacks if REDIS_URL is not set)
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_DB=0
# REDIS_PASSWORD=
```

For Redis Sentinel:

```
REDIS_URL=redis://:password@mymaster/0        # service name in path
REDIS_SENTINEL_HOSTS=sentinel-1,sentinel-2    # hostnames/IPs, comma-separated
REDIS_SENTINEL_PORT=26379
```

## 3) What gets enabled

- Redis-backed server sessions: JWT `jti` is allowlisted in Redis with expiry.
  - Login/Signup/Trusted header auth/LDAP logins create a session record.
  - Logout/Signout revokes the session immediately.
  - Optional sliding TTL refresh on verified requests.
- Fast chat cache endpoint: returns the latest N chat titles from cache, default 3.

## 4) Endpoints

- Create session (sign in):

```
POST /api/v1/auths/signin
{"email":"admin@localhost","password":"admin"}
```

- Sign out (revokes session immediately):

```
GET  /api/v1/auths/signout
POST /api/v1/auths/logout
```

- Fast chat list (from cache, default 3):

```
GET /api/v1/chats/fast          # Authorization: Bearer <token> or cookie
GET /api/v1/chats/fast?count=5  # limit 1..10, TTL ~60s
```

- Cache health (diagnostic):
```
GET /api/v1/utils/cache/ping
```

## 5) Manual verification

1. Start Redis:
```
docker run -p 6379:6379 --name redis -d redis:7
```

2. Start backend and sign in to get a token (or cookie). Then:

- Verify a session key like `open-webui:session:<jti>` exists in Redis.
- Open/refresh the app; with `SESSION_SLIDING_TTL=True`, the key expiry should refresh.
- Call `GET /api/v1/chats/fast` twice; the second call should be served from cache.
- Create, update, pin, archive, clone, or delete a chat and check that `chats/fast`
  reflects the change immediately (invalidation is triggered on mutations).

## 6) Notes

- Source of truth remains the database; Redis is a performance layer.
- If Redis is down, the app still works, but sessions allowlisting and fast-cache will be bypassed.
- aiocache is configured from `REDIS_URL` (or REDIS_HOST/PORT/DB/PASSWORD) automatically.

## 7) Troubleshooting

- `GET /api/v1/utils/cache/ping` returns `{ "ok": false }`:
  - Check `REDIS_URL` and connectivity; inspect backend logs.
- Session not created:
  - Ensure `ENABLE_REDIS_SESSIONS=True` and JWT contains a `jti`.
- Fast cache stale:
  - Confirm Redis connection; otherwise the endpoint falls back to DB.
