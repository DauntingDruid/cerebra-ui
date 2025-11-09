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

# Clear all chat cache keys
docker exec -it redis sh -lc "redis-cli --scan --pattern 'open-webui:chat-cache:*' | xargs -r redis-cli DEL"
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
python3 test/test_files/chat_cache_bench.py \
  --chat-id "$CHAT_ID" \
  --token "$WEBUI_TOKEN" \
  --clear-redis \
  --user-id "$USER_ID" \
  --warm-runs 5 \
  --expect-speedup 1.5 \
  --show-keys

# Optional JSON output for CI tools
python3 test/test_files/chat_cache_bench.py \
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
python3 test/test_files/chat_cache_bench.py \
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




## 11) Automated chat‑cache tests (backend suite)

Run a fast suite that covers speedup, TTL, LRU behavior, auth/errors, and Redis downtime.

### Test Categories

Tests are organized into three categories:

- **Unit Tests** (t2-t7): Cache functionality and behavior
  - `t2`: Cache snapshot creation + TTL
  - `t3`: Warm GET stability
  - `t4`: TTL expiry and repopulation
  - `t5`: LRU move-to-front behavior
  - `t6`: LRU cap eviction
  - `t7`: Cache clearing behavior

- **Performance Tests** (t1, t11-t13): Speed and latency measurements
  - `t1`: Cold vs warm speedup
  - `t11`: Concurrent load performance (multiple simultaneous requests)
  - `t12`: Cache hit rate performance (consistency across multiple hits)
  - `t13`: Large payload performance (performance with large chat data)

- **Integration Tests** (t8-t10): Error handling, auth, and system resilience
  - `t8`: Nonexistent chat error handling
  - `t9`: Unauthorized access handling
  - `t10`: Redis downtime fallback

```bash
# Prereqs: Redis + WebUI running; obtain CHAT_ID, USER_ID, WEBUI_TOKEN
export WEBUI_TOKEN='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjQ4N2VkMTUzLTkyNTctNGVlMS05YWJjLWMwNzE2MmE3NDkyZSJ9.yqU2RpwarO37KzuJMUNd3X_Yk38sgLHab6VyTkbtIwE'
export USER_ID=487ed153-9257-4ee1-9abc-c07162a7492e
export CHAT_ID=593c3625-d732-478f-9412-39241cb610f7
export CHAT_ID_B=d361a777-df87-4e7d-adca-bc059ba2fe06
export CHAT_ID_C=489302e9-761f-4076-a0f0-7be0a85f15df
export CHAT_ID_D=d66f7090-8dcd-41e9-abd4-97d4b69fa33e

python3 test/test_files/chat_cache_bench.py \
  --suite all \
  --chat-id "$CHAT_ID" \
  --user-id "$USER_ID" \
  --token "$WEBUI_TOKEN" \
  --extra-chat-ids "${CHAT_ID_B},${CHAT_ID_C},${CHAT_ID_D}" \
  --recent-limit 3 \
  --allow-redis-restart

# Run ALL tests (t1..t10). LRU tests (t5,t6) are skipped unless extra IDs are provided.
python3 test/test_files/chat_cache_bench.py \
  --suite all \
  --chat-id "$CHAT_ID" \
  --user-id "$USER_ID" \
  --token "$WEBUI_TOKEN" \
  --extra-chat-ids "${CHAT_ID_B},${CHAT_ID_C},${CHAT_ID_D}" \
  --recent-limit 3 \

# Run tests by category
python3 test/test_files/chat_cache_bench.py \
  --suite unit \
  --chat-id "$CHAT_ID" \
  --user-id "$USER_ID" \
  --token "$WEBUI_TOKEN" \
  --extra-chat-ids "${CHAT_ID_B},${CHAT_ID_C},${CHAT_ID_D}"

python3 test/test_files/chat_cache_bench.py \
  --suite performance \
  --chat-id "$CHAT_ID" \
  --user-id "$USER_ID" \
  --token "$WEBUI_TOKEN"

# Run specific performance tests with custom parameters
python3 test/test_files/chat_cache_bench.py \
  --suite t11 \
  --chat-id "$CHAT_ID" \
  --token "$WEBUI_TOKEN" \
  --concurrent-requests 20 \
  --max-latency-ms 1000

python3 test/test_files/chat_cache_bench.py \
  --suite t12 \
  --chat-id "$CHAT_ID" \
  --token "$WEBUI_TOKEN" \
  --cache-hit-runs 50

python3 test/test_files/chat_cache_bench.py \
  --suite integration \
  --chat-id "$CHAT_ID" \
  --user-id "$USER_ID" \
  --token "$WEBUI_TOKEN" \
  --allow-redis-restart

# Run multiple categories
python3 test/test_files/chat_cache_bench.py \
  --suite unit,performance \
  --chat-id "$CHAT_ID" \
  --user-id "$USER_ID" \
  --token "$WEBUI_TOKEN" \
  --extra-chat-ids "${CHAT_ID_B},${CHAT_ID_C},${CHAT_ID_D}"

# Example selective run (specific tests)
python3 test/test_files/chat_cache_bench.py \
  --suite t1,t2,t4,t8,t9 \
  --chat-id "$CHAT_ID" \
  --user-id "$USER_ID" \
  --token "$WEBUI_TOKEN"

# Redis downtime test (t10) is SAFE no-op but will stop/start the Redis container.
# Enable it explicitly:
python3 test/test_files/chat_cache_bench.py \
  --suite t10 \
  --chat-id "$CHAT_ID" \
  --user-id "$USER_ID" \
  --token "$WEBUI_TOKEN" \
  --allow-redis-restart
```

Notes:
- Tests are categorized as: **Unit** (t2-t7), **Performance** (t1, t11-t13), **Integration** (t8-t10)
- Run by category: `--suite unit`, `--suite performance`, or `--suite integration`
- Performance test parameters:
  - `--concurrent-requests N`: Number of concurrent requests for t11 (default: 10)
  - `--max-latency-ms N`: Maximum acceptable latency for t11 in ms (default: 500)
  - `--cache-hit-runs N`: Number of cache hit requests for t12 (default: 20)
- LRU limit defaults to 3; override with `--recent-limit` if configured differently.
- Tests print concise PASS/FAIL/SKIP lines with category labels and return non‑zero on any failure.
- `t5` needs ≥1 extra chat ID; `t6` needs ≥3; missing inputs will SKIP those tests.
- For payload stability (`t3`), only basic checks are performed to avoid flakiness.