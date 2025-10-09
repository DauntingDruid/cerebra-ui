# backend/open_webui/routers/betterauth_adapter.py
import os
import json
import psycopg
from psycopg.rows import dict_row
import aiohttp
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from open_webui.env import (
    WEBUI_SESSION_COOKIE_SAME_SITE,
    WEBUI_SESSION_COOKIE_SECURE,
)

DATABASE_URL = os.getenv("DATABASE_URL")

router = APIRouter(prefix="/api/v1/auths", tags=["auths"])

BETTERAUTH_BASE_URL = os.getenv(
    "BETTERAUTH_BASE_URL",
    "http://betterauth-service-betterauth-1:4000",
).rstrip("/")


def bootstrap_role(email: str) -> dict:
    """Return role/status/is_active based on whether this is the first user."""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # lock to avoid race conditions
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('bootstrap_admin'))")
            cur.execute('SELECT COUNT(*) AS c FROM "user"')
            n = cur.fetchone()["c"]

            if n == 0:
                return {"role": "admin", "status": "active", "is_active": True}
            return {"role": "user", "status": "pending", "is_active": False}
        

def _string_error(data, fallback="Request failed"):
    """Extract a human-readable error string from various shapes."""
    if isinstance(data, dict):
        for k in ("detail", "error", "message"):
            if data.get(k):
                v = data[k]
                return v if isinstance(v, str) else json.dumps(v)
        return json.dumps(data)
    if isinstance(data, (list, tuple)):
        return json.dumps(data)
    if data is None:
        return fallback
    return str(data)


async def _post_json(path: str, payload: dict):
    if not BETTERAUTH_BASE_URL:
        raise HTTPException(status_code=500, detail="BETTERAUTH_BASE_URL not configured")

    url = f"{BETTERAUTH_BASE_URL}{path}"
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, json=payload) as resp:
            try:
                data = await resp.json()
            except Exception:
                text = await resp.text()
                data = {"message": text}

            if resp.status >= 400:
                raise HTTPException(
                    status_code=resp.status,
                    detail=_string_error(data, fallback=f"HTTP {resp.status}"),
                )
            return data


async def _get_text(path: str, query: dict):
    """GET that may return plain text (BetterAuth verify endpoint)."""
    if not BETTERAUTH_BASE_URL:
        raise HTTPException(status_code=500, detail="BETTERAUTH_BASE_URL not configured")

    qs = urlencode(query or {})
    url = f"{BETTERAUTH_BASE_URL}{path}?{qs}"
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(url) as resp:
            txt = await resp.text()
            if resp.status >= 400:
                # try to parse JSON; fall back to text
                try:
                    dj = json.loads(txt)
                    msg = _string_error(dj, txt)
                except Exception:
                    msg = txt
                raise HTTPException(status_code=resp.status, detail=msg)
            return txt


def _normalize_user(u: dict, email_fallback: str = "") -> dict:
    email = (u or {}).get("email") or email_fallback
    name = (u or {}).get("name") or (email.split("@")[0] if email else "")
    return {
        "id": (u or {}).get("id") or (u or {}).get("_id") or email,
        "email": email,
        "name": name,
        "role": (u or {}).get("role") or "user",
    }


def _json_ok_with_cookie(user: dict, token: str | None):
    """Return {status:true, user, token} and set a JS-readable 'token' cookie."""
    resp = JSONResponse({"status": True, "user": user, "token": token})
    if token:
        resp.set_cookie(
            "token",
            token,
            httponly=False,  # UI reads it via JS in dev
            samesite=WEBUI_SESSION_COOKIE_SAME_SITE,
            secure=WEBUI_SESSION_COOKIE_SECURE,
            path="/",
        )
    return resp


# @router.post("/signin")
# async def signin(payload: dict, request: Request):
#     email = (payload or {}).get("email", "").strip().lower()
#     password = (payload or {}).get("password", "")
#     if not email or not password:
#         raise HTTPException(status_code=400, detail="Email and password required")

#     ba = await _post_json("/api/auth/login", {"email": email, "password": password})
#     token = ba.get("token") or ba.get("access_token")
#     user = _normalize_user(ba.get("user"), email_fallback=email)
#     #user["role"] = "admin"
#     if not token or not user.get("email"):
#         raise HTTPException(status_code=500, detail="Login payload missing token or user")

#     return _json_ok_with_cookie(user, token)



@router.post("/signin")
async def signin(payload: dict, request: Request):
    email = (payload or {}).get("email", "").strip().lower()
    password = (payload or {}).get("password", "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    ba = await _post_json("/api/auth/login", {"email": email, "password": password})
    token = ba.get("token") or ba.get("access_token")
    user = _normalize_user(ba.get("user"), email_fallback=email)

    # 🔹 Check status
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute('SELECT status, is_active, role FROM "user" WHERE email = %s', (email,))
        u = cur.fetchone()
        if not u or not u["is_active"] or u["status"] != "active":
            raise HTTPException(status_code=403, detail="Account pending admin approval")

    return _json_ok_with_cookie(user, token)


@router.post("/signup")
async def signup(payload: dict, request: Request):
    name = (payload or {}).get("name") or ""
    email = (payload or {}).get("email", "").strip().lower()
    password = (payload or {}).get("password", "")
    profile_image_url = (payload or {}).get("profile_image_url") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Name, email, and password required")

    # Call BetterAuth signup
    ba = await _post_json(
        "/api/auth/signup",
        {"name": name, "email": email, "password": password, "profile_image_url": profile_image_url},
    )

    token = ba.get("token") or ba.get("access_token")
    user = _normalize_user(ba.get("user") or {"email": email, "name": name, "role": "user"}, email_fallback=email)

    # 🔹 Decide role/status/is_active
    decide = bootstrap_role(email)
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            '''UPDATE "user"
               SET role = %s, status = %s, is_active = %s, updatedAt = NOW()
             WHERE email = %s''',
            (decide["role"], decide["status"], decide["is_active"], email)
        )
        conn.commit()

    return _json_ok_with_cookie({**user, **decide}, token)


# @router.post("/signup")
# async def signup(payload: dict, request: Request):
#     name = (payload or {}).get("name") or ""
#     email = (payload or {}).get("email", "").strip().lower()
#     password = (payload or {}).get("password", "")
#     profile_image_url = (payload or {}).get("profile_image_url") or ""
#     if not email or not password:
#         raise HTTPException(status_code=400, detail="Name, email, and password required")

#     ba = await _post_json(
#         "/api/auth/signup",
#         {"name": name, "email": email, "password": password, "profile_image_url": profile_image_url},
#     )

#     # BetterAuth may omit token until email is verified
#     token = ba.get("token") or ba.get("access_token")
#     user = _normalize_user(ba.get("user") or {"email": email, "name": name, "role": "user"}, email_fallback=email)
#     #user["role"] = "admin"
#     return _json_ok_with_cookie(user, token)


@router.post("/send-verification")
async def send_verification(payload: dict):
    """
    Body: { "email": "user@example.com" }
    Returns: { "status": true, "message": "..."}
    """
    email = (payload or {}).get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    await _post_json("/api/auth/request-verification", {"email": email})
    return JSONResponse({"status": True, "message": "Verification email sent if account exists."})


@router.post("/verify-email")
async def verify_email(payload: dict):
    """
    Body: { "token": "...", "email": "user@example.com" }
    Returns: { "status": true, "message": "..."}
    """
    token = (payload or {}).get("token", "")
    email = (payload or {}).get("email", "").strip().lower()
    if not token or not email:
        raise HTTPException(status_code=400, detail="token and email are required")

    txt = await _get_text("/api/auth/verify", {"token": token, "email": email})
    return JSONResponse({"status": True, "message": txt or "Email verified"})



@router.patch("/approve")
async def approve_user(payload: dict):
    email = (payload or {}).get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            '''UPDATE "user"
               SET status = 'active', is_active = true
             WHERE email = %s''',
            (email,)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        conn.commit()

    return {"status": True, "message": f"User {email} approved"}



@router.get("/signout")
async def signout():
    return JSONResponse({"status": True})
