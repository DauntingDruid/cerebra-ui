# Redis Chat Cache – Demo Script (CS59)

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


