# 🚀 CerebraUI Setup Guide

> **CS59 Capstone Project - Open Source AI Interface**

---

## ⚡ Quick Start
- **📋 Prerequisite**: Docker Desktop installed and running
- **📁 Clone and enter folder**:
```bash
git clone <your-repo-url>
cd "[your_folder]/cerebra-ui"
```
- **🚀 Pull & start services**: 
```bash
OPEN_WEBUI_PORT=3000 docker compose pull && OPEN_WEBUI_PORT=3000 docker compose up -d
```
- **⏳ Wait for startup** (5-10 mins on first run - downloading embedding models):
```bash
# Check container health
docker ps --format "{{.Names}}\t{{.Status}}" | grep open-webui

# Monitor progress
docker logs -f open-webui | grep -E "(Fetching|files)"
```

### ✅ Success Indicators
- Container shows "Up X minutes (healthy)"
- Logs show "Fetching 30 files: 100%"
- `curl -I http://localhost:3000` returns "HTTP/1.1 200 OK"

- **🌐 Open the app**: http://localhost:3000 (only after container shows "healthy")

### 🤖 Pull a Model (Ollama)
```bash
docker exec -it ollama ollama pull llama3.1:8b
```

---

## 🔧 Daily Commands
```bash
# Status
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Ports}}" | egrep "^(open-webui|ollama|redis)\b"

# Redis CLI to check if Redis is running
docker exec -it redis redis-cli PING

# Run Redis CLI 
docker exec -it redis redis-cli

# Logs
docker logs -f open-webui | cat

# Update images & restart
docker compose pull && docker compose up -d

# Stop
docker compose down

# Reset (removes data volumes)
docker compose down -v
```


-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

### 📝 Notes
- Compose includes `ollama`, `open-webui`, and `redis`. No extra setup needed.
- If port 3000 or 6380 is in use, change `OPEN_WEBUI_PORT` (start command) or edit `docker-compose.yaml` port mappings.

### 💾 Redis Chat Cache (Demo-ready)
- Enabled by default via env in `docker-compose.yaml` and `docker-compose.override.yaml`:
  - `ENABLE_CHAT_CACHE=true`
  - `CHAT_CACHE_MAX_RECENT=3` (cache kept for your 3 most recent opened chats)
  - `CHAT_CACHE_TTL_SECONDS=900` (15 minutes TTL)

How it works:
- When you open a chat, its latest snapshot is cached in Redis.
- On subsequent opens, the chat loads from cache first; DB remains source of truth.
- When a new assistant message is saved, the cache is refreshed automatically.

Quick verification (local):
```bash
# 1) Start stack
OPEN_WEBUI_PORT=3000 docker compose -f docker-compose.yaml -f docker-compose.override.yaml up -d --build --force-recreate

# 2) Health check
docker ps --format "{{.Names}}\t{{.Status}}" | grep open-webui
curl -I http://localhost:3000 | head -1

# 3) Open the UI, create a chat, send 2-3 messages, note chat_id from URL

# 4) Warm the cache by viewing the same chat twice
# (observe faster reload on second open)

# 5) Verify Redis keys (optional)
docker exec -it redis redis-cli KEYS 'open-webui:chat-cache:*'

# 6) Test LRU eviction
# Open 4th chat; the oldest of the prior 3 cached chats gets evicted
docker exec -it redis redis-cli LRANGE open-webui:chat-cache:recent:<your_user_id> 0 -1

# 7) Confirm refresh after message
# Send a new message; cache snapshot is updated automatically
docker exec -it redis redis-cli GET open-webui:chat-cache:item:<chat_id> | head -c 200
```

Disable temporarily (optional):
```bash
OPEN_WEBUI_PORT=3000 ENABLE_CHAT_CACHE=false docker compose up -d
```

---

## 🚨 Troubleshooting

### ❌ *Error Case 1: Free up space*
```
Error response from daemon: No space left on device
```

**🔧 Solution:**
Free up space:
```bash
docker system prune -af --volumes
```

### ❌ *Error Case 2: Container Name Conflict*
```
Error response from daemon: Conflict. The container name "/ollama" is already in use
Error response from daemon: Conflict. The container name "/redis" is already in use
```

**🔧 Solution:**
Reset: Remove all containers and volumes (if error occurs)
    ```bash
    # from the project root
    docker rm -f redis open-webui ollama || true
    OPEN_WEBUI_PORT=3000 docker compose up -d
    ```

### ❌ *Error Case 3: 500 Internal Error (Embedding Download)*
```
- Browser shows "500: Internal Error" when accessing http://localhost:3000
- Container shows "Up X minutes (unhealthy)" status  
- Logs show "Fetching 30 files: 0%" stuck at 0% for a long time
```

**🔧 Solution:**
The app is downloading embedding models (30 files, several GB). This can be slow or stuck on slow connections.

**⚠️ Note**: Disabling embeddings is *not recommended* as they're needed for:
- AI agent workflow integration
- Enhanced web search & document processing  
- RAG capabilities for document upload/querying

**⚡ Quick fix** - Disable embeddings to start faster for checking functionality *(NOT RECOMMENDED FOR CS59 PROJECT)*:
```bash
# Stop containers
docker compose down

# Edit docker-compose.yaml and add this line under open-webui environment:
# - ENABLE_EMBEDDING=false

# Restart
OPEN_WEBUI_PORT=3000 docker compose up -d

# Wait 1-2 minutes, then check:
docker ps --format "{{.Names}}\t{{.Status}}" | grep open-webui
# Should show "healthy" instead of "unhealthy"
```

**✅ Recommended approach** - Wait for download to complete (can take 10-30 minutes):
```bash
# Monitor progress
docker logs -f open-webui | grep -E "(Fetching|files)"

# Wait until you see "Fetching 30 files: 100%" then test:
curl -I http://localhost:3000
# Should return "HTTP/1.1 200 OK"

# Verify full functionality
docker ps --format "{{.Names}}\t{{.Status}}" | grep open-webui
# Should show "healthy" status
```

**✅ Verified working** - Full CerebraUI functionality with embeddings enabled for CS59 project requirements.

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

## 🔄 *Complete Restart & Verification*

### 🧹 Step 1: Clean Shutdown
```bash
docker compose down -v
```
**✅ Removes all containers and volumes for fresh start**

### 🚀 Step 2: Fresh Start
```bash
OPEN_WEBUI_PORT=3000 docker compose pull && OPEN_WEBUI_PORT=3000 docker compose up -d
```
**✅ Updates images and starts all services**

### ⏳ Step 3: Wait for Startup
```bash
sleep 30  # Wait for containers to initialize
```

### 📊 Step 4: Check Container Status
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(open-webui|ollama|redis)"
```
**✅ Should show all 3 containers running**

### 🔍 Step 5: Monitor Embedding Download
```bash
docker logs open-webui 2>&1 | grep -E "(Fetching|files)" | tail -3
```
**✅ Shows embedding download progress**

### 🧪 Step 6: Test Redis Connection
```bash
docker exec -it redis redis-cli PING
```
**✅ Should return "PONG"**

### 🌐 Step 7: Test Web Interface
```bash
curl -I http://localhost:3000 2>/dev/null | head -1
```
**✅ Should return HTTP status when ready**

### 🤖 Step 8: Test Ollama Connection
```bash
docker exec -it ollama ollama list
```
**✅ Should show available models (empty initially)**

### 📈 Monitor Progress (Optional)
```bash
# Check container health
docker ps --format "{{.Names}}\t{{.Status}}" | grep open-webui

# Monitor embedding progress
docker logs -f open-webui | grep -E "(Fetching|files)"
```

**⏰ Expected Timeline:**
- **Worst case: 20-30 minutes** for embedding download to complete
- **Web interface** will be accessible at http://localhost:3000 once healthy


-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

## 👥 Team Development Workflow (CS59)

### 🌿 Feature Branch Names
Each team member should create their feature branch from `pin/0.6.5v`:

```bash
# Frontend & UI
feat/jiayi-frontend-components

# Authentication & Security  
feat/sadman-betterauth-integration
feat/tasnim-auth-hardening

# AI & Workflows
feat/matthew-langflow-integration
feat/perry-comfyui-deployment

# Search & Engines
feat/tongfangzhu-search-apis

# Infrastructure & Caching
feat/abhishek-redis-sessions
```

### 🔄 Git Workflow Commands
```bash
# 1. Clone and setup
git clone <your-repo-url>
cd "capstone project/cerebra-ui"

# 2. Switch to stable base branch
git checkout pin/0.6.5v
git pull origin pin/0.6.5v

# 3. Create your feature branch
git checkout -b feat/[your-name]-[feature]
# Example: git checkout -b feat/sadman-betterauth-integration

# 4. Start development
OPEN_WEBUI_PORT=3000 docker compose up -d
# Wait for embeddings, then start coding

# 5. Commit and push your work
git add .
git commit -m "feat: [brief description of your feature]"
git push origin feat/[your-name]-[feature]

# 6. Create Pull Request to pin/0.6.5v when ready
```

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

## 🔄 *Unified Local Development Workflow* (frontend + backend)

This single workflow builds a local image (so new Python deps work), bind-mounts your backend and static assets for quick iteration, and supports frontend changes reliably.

1) Make sure your deps are declared
- Frontend deps: `package.json`
- Backend deps: `backend/requirements.txt` (pin versions)

2) Start (builds local image with increased Node memory)
```bash
OPEN_WEBUI_PORT=3000 docker compose -f docker-compose.yaml -f docker-compose.override.yaml up -d --build --force-recreate
```

3) Iterate
- Backend code (Python): saved changes are live via the bind mount
- Frontend code (Svelte): run this from the **project root** to build UI and restart:
```bash
npm run build && OPEN_WEBUI_PORT=3000 docker compose -f docker-compose.yaml -f docker-compose.override.yaml up -d --force-recreate
```

4) Verify
```bash
docker inspect -f '{{.Config.Image}}' open-webui          # should show cerebra-ui:local
docker exec -it open-webui python -c "import pkgutil,sys;print('redis' in [m.name for m in pkgutil.iter_modules()])"
```

5) Theme (optional)
```js
localStorage.theme = 'light'; location.reload();
```

Notes:
- The override now builds a local image (`cerebra-ui:local`) so new Python deps in `backend/requirements.txt` are installed automatically.
- Backend and `static/` are bind-mounted for fast iteration. Frontend edits require `npm run build` before a quick `docker compose up -d --force-recreate`.


## 🚨 Troubleshooting

### ❌ *Error Case 1: 500 Internal Error (Embedding Download)*
```bash
npm ci && NODE_OPTIONS=--max-old-space-size=4096 npm run build && OPEN_WEBUI_PORT=3000 docker compose -f docker-compose.yaml -f docker-compose.override.yaml up -d --build --force-recreate
```