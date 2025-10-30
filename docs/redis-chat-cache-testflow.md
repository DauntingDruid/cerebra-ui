# Redis Chat Cache – Demo Script (CS59)

## Backend Redis touchpoints (quick reference)

- `backend/open_webui/utils/chat_cache.py`: Redis-backed chat cache helpers (item snapshot + per-user recent LRU, TTL, safe no-op on Redis errors).
- `backend/open_webui/config.py`: `AppConfig` wiring to Redis; mirrors config keys into Redis and reads back; defines `ENABLE_CHAT_CACHE` persistent config.
- `backend/open_webui/env.py`: Environment variables for Redis (`REDIS_URL`, `REDIS_SENTINEL_HOSTS`, `REDIS_SENTINEL_PORT`, `WEBSOCKET_REDIS_URL`, lock timeout flags).
- `backend/open_webui/main.py`: Creates `AppConfig` with `REDIS_URL`/sentinels and sets `ENABLE_CHAT_CACHE` on `app.state.config`.
- `backend/open_webui/utils/redis.py`: Connection helpers (direct + Sentinel) and env parsing for sentinel URLs.
- `backend/open_webui/socket/utils.py`: `RedisDict` (hash-backed map) and `RedisLock` (simple lock with TTL) used by websocket infra.
- `backend/open_webui/socket/main.py`: Websocket pools/managers on Redis when `WEBSOCKET_MANAGER=redis` (session/user/usage pools, cleanup lock).
- `backend/open_webui/routers/chats.py`: Integrates chat cache operations (`get_cached_chat`, `set_cached_chat`, `touch_recent`, etc.).

This short script verifies the Redis-backed chat cache, shows cache warming, proves the latency improvement, and demonstrates the 3-chat LRU behavior. Estimated time: 5–6 minutes.

## 0) Prerequisites

```bash
# Start services
OPEN_WEBUI_PORT=3000 docker compose -f docker-compose.yaml -f docker-compose.override.yaml up -d --force-recreate

# Make sure services are running
docker ps --format "{{.Names}}\t{{.Status}}" | grep -E "open-webui|redis"

# Redis must respond
docker exec -it redis redis-cli PING

# Confirm cache config in the running app
docker exec -it open-webui env | egrep 'REDIS_URL|ENABLE_CHAT_CACHE|CHAT_CACHE_'
```

## 1) Set your chat ID

Use any existing chat ID (copy from the browser URL when viewing a chat).

```bash
CHAT_ID=<your_chat_id>
```

## 2) Cold start (clear just this chat cache)

```bash
docker exec -it redis redis-cli DEL open-webui:chat-cache:item:$CHAT_ID
docker exec -it redis redis-cli TTL open-webui:chat-cache:item:$CHAT_ID   # expect -2 (missing)
```

## 3) Warm the cache (browser)

Open the chat once in your browser:

```
http://localhost:3000/c/$CHAT_ID
```

## 4) Show cache populated

```bash
docker exec -it redis redis-cli KEYS 'open-webui:chat-cache:*'
docker exec -it redis redis-cli GET open-webui:chat-cache:item:$CHAT_ID | head -c 200
docker exec -it redis redis-cli TTL open-webui:chat-cache:item:$CHAT_ID   # expect > 0
```

## 5) Show per-user recent LRU list (max 3)

```bash
# Find your user’s list key
docker exec -it redis redis-cli KEYS 'open-webui:chat-cache:recent:*'

# Replace <user_id> with the printed value
docker exec -it redis redis-cli LRANGE open-webui:chat-cache:recent:<user_id> 0 -1
```

Tip: A chat is added to the “recent” list when you open its page (GET /api/v1/chats/{id}). Creating/sending messages alone doesn’t add it until you view that chat page.

## 6) Speed-up proof (browser) (DOES NOT WORK IN LOCAL ENVIRONMENT)

1. Open DevTools → Network → reload the chat page.
2. Click the request to `/api/v1/chats/$CHAT_ID` and show response header `X-Process-Time`.
3. Compare first load (cold) vs second load (warm) – the warm load should be faster.

## 7) LRU behavior demo (top 3) (DOES NOT WORK IN LOCAL ENVIRONMENT)

1. Open two more distinct chat pages; verify they appear in the recent list.
2. Open a 4th distinct chat page.

```bash
docker exec -it redis redis-cli LRANGE open-webui:chat-cache:recent:<user_id> 0 -1
docker exec -it redis redis-cli KEYS 'open-webui:chat-cache:item:*'
```

Result: The oldest of the prior 3 is evicted from the LRU list; its `item:` key will also be removed.

## 8) Troubleshooting (quick)

```bash
# Ensure app is healthy
docker ps --format "{{.Names}}\t{{.Status}}" | grep open-webui

# Confirm envs are present in the running container
docker exec -it open-webui env | egrep 'REDIS_URL|ENABLE_CHAT_CACHE|CHAT_CACHE_'

# Confirm the chat route was hit (replace with your CHAT_ID)
docker logs -n 400 open-webui | grep -E "/api/v1/chats/$CHAT_ID|ERROR|Traceback"
```

If the recent list is empty, make sure you actually opened each chat page at least once in the browser.



## 9) Scripted cold vs warm benchmark (local)

Use the helper script to measure cold vs warm loads and print a verdict.

```bash
# 0) Ensure Redis + WebUI are running (you can skip Ollama):
OPEN_WEBUI_PORT=3000 docker compose -f docker-compose.yaml -f docker-compose.override.yaml up -d --no-deps redis open-webui

# 1) Open a chat in the UI twice and copy its CHAT_ID from the URL (/c/<CHAT_ID>)
#    Optionally get USER_ID from Redis recent key
docker exec -it redis redis-cli KEYS 'open-webui:chat-cache:recent:*'

# 2) Set env vars (paste your cookie token from the browser: DevTools → Application → Cookies → token → copy value)
export WEBUI_TOKEN='<your_token>'
export CHAT_ID=<your_chat_id>
export USER_ID=<your_user_id>

# Example values
export WEBUI_TOKEN='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImVkNDQ5NzEyLWE4ODYtNDRjMi1iY2M5LTkyNWYzZjEyNjYxNCJ9.R8-IBOk14SrIGAI-oOEGvueq5CTv4RNyo-McA_9C8Tk'
export CHAT_ID=149df51e-28fc-431e-b9cb-39e9e408d5b0
export USER_ID=ed449712-a886-44c2-bcc9-925f3f126614

# 3) Run the bench (clears this chat’s snapshot, then does cold+multiple warm GETs)
python3 test/chat_cache_bench.py \
  --chat-id "$CHAT_ID" \
  --token "$WEBUI_TOKEN" \
  --clear-redis \
  --user-id "$USER_ID" \
  --warm-runs 5 \
  --expect-speedup 1.5 \
  --show-keys

# Optional JSON output for CI tools
python3 test/chat_cache_bench.py \
  --chat-id "$CHAT_ID" \
  --token "$WEBUI_TOKEN" \
  --warm-runs 5 \
  --json

# Example output
# COLD  status=200 header=0s measured=0.160s
# WARM1 status=200 header=0s measured=0.021s
# WARM2 status=200 header=0s measured=0.017s
# WARM3 status=200 header=0s measured=0.018s
# Verdict: cache_warm_faster by x9.23 (median of 3 runs)
# Assert: expected ≥ x1.50 → PASS
```

Notes:
- If the `X-Process-Time` header shows `0s` (integer rounding), use the measured times.
- 401 Unauthorized → set a valid `WEBUI_TOKEN` (browser cookie `token`).
- If keys don’t appear, open the chat page once in the browser to warm the cache first.

### Pretty mode (optional, with boxes and icons)

```bash
pip install rich

# Pretty output is used automatically if installed; disable with --no-pretty
python3 test/chat_cache_bench.py \
  --chat-id "$CHAT_ID" \
  --token "$WEBUI_TOKEN" \
  --warm-runs 3 \
  --expect-speedup 1.5

# Example (pretty mode)
# ─ Chat Cache Timing ─────────────────────────────────────────────
# 🧊 Cold   ✅   header: 0s     measured: 0.160s   effective: 0.160s
# 🔥 Warm 1 ✅   header: -      measured: 0.021s   effective: 0.021s
# 🔥 Warm 2 ✅   header: -      measured: 0.017s   effective: 0.017s
# 🔥 Warm 3 ✅   header: -      measured: 0.018s   effective: 0.018s
# ─ PASS ─────────────────────────────────────────────────────────
# Speedup: x9.23
# Expected: ≥ x1.50
# Warm median: 0.018s
# Cold: 0.160s
```



