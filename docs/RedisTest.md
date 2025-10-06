**1: Start the project locally (with Redis)**
*Start Redis*
docker run --name cerebra-redis -p 6379:6379 -d  redis:7

**2: Set env (create .env in project root)**
cat > .env << 'EOF'
REDIS_URL=redis://localhost:6379/0
ENABLE_REDIS_SESSIONS=True
SESSION_SLIDING_TTL=True
JWT_EXPIRES_IN=60s
RESET_CONFIG_ON_START=True
ENABLE_SIGNUP=True
ENABLE_LOGIN_FORM=True
EOF

@Notes:
*One-time bootstrap (first run only, then remove from .env)*
- RESET_CONFIG_ON_START=True is important to avoid issues with the config.
- ENABLE_SIGNUP=True is important to allow signup.
- ENABLE_LOGIN_FORM=True is important to allow login.
*Flow:*
1) Start normally for the very first boot → create admin.
2) Remove the bootstrap flags and restart. From then on, no manual redis-cli or flags needed.

**3: Install and run backend**
*run backend in root directory (RECOMMENDED)*
cd "/Users/abhishektomar/Desktop/capstone project/cerebra-ui"
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend uvicorn open_webui.main:app --reload --host 0.0.0.0 --port 8080

@ If you want to reset the config on start, then you need to export the following variables in the terminal:
export RESET_CONFIG_ON_START=True ENABLE_SIGNUP=True ENABLE_LOGIN_FORM=True

*Run backend in backend directory (ALTERNATIVE)*
cd "/Users/abhishektomar/Desktop/capstone project/cerebra-ui/backend"
uvicorn open_webui.main:app --reload --host 0.0.0.0 --port 8080

@Optional: read full setup in docs/RedisSetup.md


**DEBUGGING**
@if you get 403 Forbidden error, then you need to debug the issue.
*Check if your DB exists and how many users you have (from backend/)*
ls -l data/webui.db
sqlite3 data/webui.db "select count(*) from auth;"

*If /auths/signup returns 403 (signup disabled via Redis override)*
```
# Inspect overrides
docker exec -it cerebra-redis redis-cli GET open-webui:config:ENABLE_SIGNUP
docker exec -it cerebra-redis redis-cli GET open-webui:config:ENABLE_LOGIN_FORM

# Set to true (or DEL to remove overrides)
docker exec -it cerebra-redis redis-cli SET open-webui:config:ENABLE_SIGNUP true
docker exec -it cerebra-redis redis-cli SET open-webui:config:ENABLE_LOGIN_FORM true
```
Optionally force-reset DB config on next start (dev only):
```
export RESET_CONFIG_ON_START=True ENABLE_SIGNUP=True ENABLE_LOGIN_FORM=True
```


*Choose how you want to proceed*
*A) Fresh dev start (clean DB; first user becomes admin)*
  - Stop server, then (from backend/ or root directory):
  
  ```bash
  rm data/webui.db
  ```

*B) Restart Redis container*
@If you get the following error:
docker: Error response from daemon: Conflict. The container name "/cerebra-redis" is already in use by container "83a4757f5ca9b149965a1e45d1359389d22e4fdd9d4127190d987b26807e1e19". You have to remove (or rename) that container to be able to reuse that name.
See 'docker run --help'.
*Solution:*
docker stop cerebra-redis && docker rm cerebra-redis
docker run --name cerebra-redis -p 6379:6379 -d redis:7

**4: Create a user and log in (get a token)**
*Signup (first user becomes admin)*
curl -s -X POST http://localhost:8080/api/v1/auths/signup \
  -H 'Content-Type: application/json' \
  -c cookies.txt \
  -d '{"email":"admin@localhost","password":"admin","name":"Admin"}'

@Response includes token; cookies.txt stores the token cookie.

*Or sign in later*
curl -s -X POST http://localhost:8080/api/v1/auths/signin \
  -H 'Content-Type: application/json' -c cookies.txt \
  -d '{"email":"admin@localhost","password":"admin"}'

@Notes:
- !!!!*RESET_CONFIG_ON_START (set it back to False) after your first admin is created.*!!!! This is important to avoid issues with the config.
- Sessions are enforced only when `ENABLE_REDIS_SESSIONS=True` at process start.
- If you just changed this flag, fully stop and restart the API, then run SIGNIN to create the session key.
- If key list is empty but the endpoint below is 200, sessions are not enforced (still OK for other tests).

**5: Verify Redis Feature 1: Session cache (server-side allowlist)**
*Confirm a session key was created*
docker exec -it cerebra-redis redis-cli KEYS 'open-webui:session:*'

*Access a protected endpoint (works while session exists)*
curl -s http://localhost:8080/api/v1/utils/cache/ping -b cookies.txt
# {"ok": true} if aiocache+redis reachable and session valid

*Revoke the session (logout)*
curl -s -X POST http://localhost:8080/api/v1/auths/logout -b cookies.txt

*Same request should now be unauthorized*
curl -i http://localhost:8080/api/v1/utils/cache/ping -b cookies.txt
# Expect 401

*Optional: JWT header test (revocation blocks old tokens)*
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auths/signin \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@localhost","password":"admin"}' | jq -r .token)
curl -s -X POST http://localhost:8080/api/v1/auths/logout -H "Authorization: Bearer $TOKEN"
curl -i http://localhost:8080/api/v1/utils/cache/ping -H "Authorization: Bearer $TOKEN"
# Expect 401 after logout

*Optional: sliding TTL*
Set JWT_EXPIRES_IN in .env (already set to 60s above). While making authorized requests, the Redis key’s TTL will be kept near the token exp; you can inspect:
docker exec -it cerebra-redis redis-cli TTL $(docker exec -it cerebra-redis redis-cli KEYS 'open-webui:session:*' | head -n1)

**6: Verify Redis Feature 2: Fast chat cache (first 3 chats cached)**
*Create a few chats*
curl -s -X POST http://localhost:8080/api/v1/chats/new \
  -H 'Content-Type: application/json' -b cookies.txt \
  -d '{"chat":{"title":"First chat"}}'

curl -s -X POST http://localhost:8080/api/v1/chats/new \
  -H 'Content-Type: application/json' -b cookies.txt \
  -d '{"chat":{"title":"Second chat"}}'

curl -s -X POST http://localhost:8080/api/v1/chats/new \
  -H 'Content-Type: application/json' -b cookies.txt \
  -d '{"chat":{"title":"Third chat"}}'

*First call warms cache; second call hits cache (TTL ~60s by default)*
time curl -s http://localhost:8080/api/v1/chats/fast -b cookies.txt | jq .
time curl -s http://localhost:8080/api/v1/chats/fast -b cookies.txt | jq .

*See the cached key/value in Redis*
# replace USER_ID with your user id if known; otherwise list keys:
docker exec -it cerebra-redis redis-cli KEYS 'open-webui:user:*:chats:top:3'
# GET the key printed above to view JSON

*Mutation invalidates cache automatically. For example, pin a chat then fetch again:*
CID=$(curl -s http://localhost:8080/api/v1/chats/list -b cookies.txt | jq -r '.[0].id')
curl -s -X POST http://localhost:8080/api/v1/chats/$CID/pin -b cookies.txt
time curl -s http://localhost:8080/api/v1/chats/fast -b cookies.txt | jq .

*Alternatively, pin a chat using the pin endpoint*
curl -s -X POST http://localhost:8080/api/v1/chats/pin \
  -H 'Content-Type: application/json' -b cookies.txt \
  -d '{"chat_id":"1"}'

*Optional: change count*
curl -s http://localhost:8080/api/v1/chats/fast?count=5 -b cookies.txt | jq .

*Quick health check*
curl -s http://localhost:8080/api/v1/utils/cache/ping -b cookies.txt

*If anything fails, see docs/RedisSetup.md for troubleshooting.*

**7: Run tests**
PYTHONPATH=backend pytest -q backend/test/test_cache_and_sessions.py

**If you see `uvicorn: command not found`**
- You likely didn’t activate the virtualenv. From repo root:
```
source .venv/bin/activate
```
- Then run the server with the correct Python path:
```
PYTHONPATH=backend uvicorn open_webui.main:app --reload --host 0.0.0.0 --port 8080
```
- Alternatively, call uvicorn via the venv binary without activating:
```
.venv/bin/uvicorn open_webui.main:app --reload --host 0.0.0.0 --port 8080
```
- If running from the backend directory:
```
cd backend
PYTHONPATH=. uvicorn open_webui.main:app --reload --host 0.0.0.0 --port 8080
```

**If port 8080 is already in use**
```
lsof -nP -iTCP:8080 -sTCP:LISTEN
kill -9 <PID>
```

**Summary**
Redis session cache: login creates open-webui:session:<jti>; logout deletes it; revoked tokens are rejected immediately.
Redis fast chat cache: GET /api/v1/chats/fast serves top chats from Redis, auto-invalidated on chat mutations.
# {"ok": true} means aiocache -> Redis is working