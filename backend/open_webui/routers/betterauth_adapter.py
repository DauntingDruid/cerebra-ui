# backend/open_webui/routers/betterauth_adapter.py
import os, httpx
import json
import time
import datetime
import uuid
import aiohttp
import re
from typing import List
from urllib.parse import urlencode
from sqlalchemy import text
from open_webui.internal.db import get_db
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from open_webui.env import (
    WEBUI_SESSION_COOKIE_SAME_SITE,
    WEBUI_SESSION_COOKIE_SECURE,
    WEBUI_AUTH_TRUSTED_EMAIL_HEADER,
    WEBUI_AUTH_TRUSTED_NAME_HEADER,
    WEBUI_AUTH,
)
from open_webui.utils.misc import parse_duration
from open_webui.utils.auth import create_token, get_password_hash
from open_webui.utils.access_control import get_permissions
from open_webui.models.users import Users
from open_webui.models.auths import Auths, SigninForm, SignupForm
from open_webui.constants import ERROR_MESSAGES

DATABASE_URL = os.getenv("DATABASE_URL")

router = APIRouter(prefix="/api/v1/auths", tags=["auths"])

BETTERAUTH_BASE_URL = os.getenv(
    "BETTERAUTH_BASE_URL",
    "http://betterauth-service-betterauth-1:4000",
).rstrip("/")


TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET_KEY", "")

async def verify_turnstile_token(token: str, remote_ip: str | None = None):
    if not TURNSTILE_SECRET:
        raise HTTPException(status_code=500, detail="Turnstile not configured")

    data = {"secret": TURNSTILE_SECRET, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=data)
        j = res.json()
        if not j.get("success"):
            # Log error-codes if present to debug site config
            codes = j.get("error-codes")
            print("[Turnstile] verify failed:", codes)
            raise HTTPException(status_code=400, detail="Invalid Turnstile token")


def _upsert_user_bootstrap(email: str, name: str):
    """
    Ensure a row exists in Open WebUI's user table.
    Uses the existing User model from Open WebUI.
    """
    user = Users.get_user_by_email(email)
    
    if user:
        return user
    
    user_count = Users.get_num_users()
    role = "admin" if user_count == 0 else "user"
    
    return None


def _get_user_by_email(email: str):
    """Get user from database by email using Open WebUI's Users model"""
    return Users.get_user_by_email(email)
        

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
                try:
                    dj = json.loads(txt)
                    msg = _string_error(dj, txt)
                except Exception:
                    msg = txt
                raise HTTPException(status_code=resp.status, detail=msg)
            return txt


############################
# SignIn with BetterAuth
############################

@router.post("/signin")
async def signin(request: Request, response: Response, form_data: SigninForm):
    # 1) Read turnstile token from JSON (frontend must send it)
    payload = await request.json()
    ts_token = payload.get("turnstile_token")
    if not ts_token:
        raise HTTPException(status_code=400, detail="Turnstile token missing")

    # 2) Verify turnstile first
    client_ip = request.client.host if request.client else None
    await verify_turnstile_token(ts_token, client_ip)

    # Will carry through to the final response
    email_verified = True
    user = None

    if WEBUI_AUTH_TRUSTED_EMAIL_HEADER:
        if WEBUI_AUTH_TRUSTED_EMAIL_HEADER not in request.headers:
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_TRUSTED_HEADER)
        trusted_email = request.headers[WEBUI_AUTH_TRUSTED_EMAIL_HEADER].lower()
        trusted_name = request.headers.get(
            WEBUI_AUTH_TRUSTED_NAME_HEADER, trusted_email
        ) if WEBUI_AUTH_TRUSTED_NAME_HEADER else trusted_email

        if not Users.get_user_by_email(trusted_email):
            await signup(
                request, response,
                SignupForm(email=trusted_email, password=str(uuid.uuid4()), name=trusted_name)
            )

        user = Auths.authenticate_user_by_trusted_header(trusted_email)
        email_verified = True
    elif WEBUI_AUTH is False:
        admin_email = "admin@localhost"
        admin_password = "admin"
        if Users.get_user_by_email(admin_email):
            user = Auths.authenticate_user(admin_email, admin_password)
        else:
            if Users.get_num_users() != 0:
                raise HTTPException(400, detail=ERROR_MESSAGES.EXISTING_USERS)
            await signup(
                request, response,
                SignupForm(email=admin_email, password=admin_password, name="User")
            )
            user = Auths.authenticate_user(admin_email, admin_password)
        email_verified = True
    else:
        email = form_data.email.lower().strip()
        password = form_data.password

        try:
            db = next(get_db())
            row = db.execute(
                text('SELECT "emailVerified" FROM "user" WHERE LOWER(email)=LOWER(:email)'),
                {"email": email}
            ).fetchone()
            db_email_verified = bool(row[0]) if row else None
        except Exception:
            db_email_verified = None

        if db_email_verified is False:
            return {
                "token": None,
                "token_type": "Bearer",
                "expires_at": None,
                "id": None,
                "email": email,
                "name": None,
                "role": None,
                "profile_image_url": None,
                "permissions": [],
                "email_verified": False,
            }

        try:
            ba = await _post_json("/api/auth/login", {"email": email, "password": password})
            user_raw = ba.get("user") or {}
            email_verified = bool(user_raw.get("emailVerified", True))
        except HTTPException as e:
            # If BA says not verified or 403, return the pending response (no session)
            if e.status_code == 403 or "not verified" in str(e.detail).lower():
                return {
                    "token": None,
                    "token_type": "Bearer",
                    "expires_at": None,
                    "id": None,
                    "email": email,
                    "name": None,
                    "role": None,
                    "profile_image_url": None,
                    "permissions": [],
                    "email_verified": False,
                }
            # Generic invalid credentials
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)

        user = Users.get_user_by_email(email)
        if not user:
            user_count = Users.get_num_users()
            role = "admin" if user_count == 0 else request.app.state.config.DEFAULT_USER_ROLE
            hashed = get_password_hash(str(uuid.uuid4()))
            user = Auths.insert_new_auth(
                email,
                hashed,
                user_raw.get("name") or email.split("@")[0],
                user_raw.get("profile_image_url") or "/user.png",
                role,
            )
            if not user:
                raise HTTPException(500, detail="Failed to create user in local database")

    expires_delta = parse_duration(request.app.state.config.JWT_EXPIRES_IN)
    expires_at = int(time.time()) + int(expires_delta.total_seconds()) if expires_delta else None
    session_token = create_token(data={"id": user.id}, expires_delta=expires_delta)
    datetime_expires_at = (
        datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc) if expires_at else None
    )

    response.set_cookie(
        key="token",
        value=session_token,
        expires=datetime_expires_at,
        httponly=True,
        samesite=WEBUI_SESSION_COOKIE_SAME_SITE,
        secure=WEBUI_SESSION_COOKIE_SECURE,
    )

    user_permissions = get_permissions(user.id, request.app.state.config.USER_PERMISSIONS)

    return {
        "token": session_token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "profile_image_url": user.profile_image_url,
        "permissions": user_permissions,
        "email_verified": email_verified,
    }



##################################
PASSWORD_POLICY = {
    "min_length": 10,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_digit": True,
    "require_special": True,
    "forbid_spaces": True,
}


def _password_policy_issues(pw: str) -> list[str]:
    """
    Centralized password policy validation.
    Returns list of requirement messages if password fails.
    """
    issues = []
    
    if len(pw) < PASSWORD_POLICY["min_length"]:
        issues.append(f"at least {PASSWORD_POLICY['min_length']} characters")
    
    if PASSWORD_POLICY["require_uppercase"] and not re.search(r"[A-Z]", pw):
        issues.append("one uppercase letter (A–Z)")
    
    if PASSWORD_POLICY["require_lowercase"] and not re.search(r"[a-z]", pw):
        issues.append("one lowercase letter (a–z)")
    
    if PASSWORD_POLICY["require_digit"] and not re.search(r"\d", pw):
        issues.append("one number (0–9)")
    
    if PASSWORD_POLICY["require_special"] and not re.search(r"[^A-Za-z0-9]", pw):
        issues.append("one special character (!@#$…)")
    
    if PASSWORD_POLICY["forbid_spaces"] and re.search(r"\s", pw):
        issues.append("no spaces")
    
    return issues


###########################################





############################
# SignUp with BetterAuth
############################

@router.post("/signup")
async def signup(request: Request, response: Response, form_data: SignupForm):
    """
    BetterAuth-integrated signup
    """
    
    if WEBUI_AUTH:
        if (
            not request.app.state.config.ENABLE_SIGNUP
            or not request.app.state.config.ENABLE_LOGIN_FORM
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.ACCESS_PROHIBITED
            )
    else:
        if Users.get_num_users() != 0:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.ACCESS_PROHIBITED
            )

    email = form_data.email.lower()

    pw_issues = _password_policy_issues(form_data.password)
    if pw_issues:
        raise HTTPException(
            status_code=400,
            detail=f"Password must have: {', '.join(pw_issues)}."
        )
    
    if Users.get_user_by_email(email):
        raise HTTPException(400, detail=ERROR_MESSAGES.EMAIL_TAKEN)

    user_count = Users.get_num_users()
    
    role = (
        "admin" if user_count == 0 else request.app.state.config.DEFAULT_USER_ROLE
    )

    if user_count == 0:
        request.app.state.config.ENABLE_SIGNUP = False

    try:
        # Create user in BetterAuth
        await _post_json(
            "/api/auth/signup",
            {
                "name": form_data.name,
                "email": email,
                "password": form_data.password,
                "profile_image_url": form_data.profile_image_url or "",
            },
        )
        
        # Create user in Open WebUI
        hashed = get_password_hash(form_data.password)
        user = Auths.insert_new_auth(
            email,
            hashed,
            form_data.name,
            form_data.profile_image_url or "/user.png",
            role,
        )

        if not user:
            raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)

        return {
            "status": True,
            "message": "Account created successfully. Please verify your email before signing in.",
            "email": email,
        }
        
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(500, detail=f"Signup failed: {str(err)}")


############################
# Password Reset
############################

@router.post("/forgot-password")
async def forgot_password(payload: dict):
    """Request password reset email"""
    email = (payload or {}).get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    try:
        await _post_json("/api/auth/forgot-password", {"email": email, "redirectTo": "/auth/reset-password/confirm"})
        return JSONResponse({
            "status": True, 
            "message": "If an account exists with this email, a password reset link has been sent."
        })
    except HTTPException as e:
        return JSONResponse({
            "status": True, 
            "message": "If an account exists with this email, a password reset link has been sent."
        })


@router.post("/reset-password")
async def reset_password(payload: dict):
    """Reset password using token"""
    token = (payload or {}).get("token", "")
    new_password = (payload or {}).get("password", "")
    
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new password are required")
    
    pw_issues = _password_policy_issues(new_password)
    if pw_issues:
        raise HTTPException(
            status_code=400,
            detail=f"Password must have: {', '.join(pw_issues)}."
        )
    try:
        await _post_json("/api/auth/reset-password", {
            "token": token,
            "password": new_password
        })
        
        return JSONResponse({
            "status": True,
            "message": "Password has been reset successfully. You can now sign in with your new password."
        })
    except HTTPException as e:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")


############################
# Email Verification
############################

@router.post("/send-verification")
async def send_verification(payload: dict):
    """Send verification email"""
    email = (payload or {}).get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    await _post_json("/api/auth/request-verification", {"email": email})
    return JSONResponse({"status": True, "message": "Verification email sent if account exists."})


@router.post("/verify-email")
async def verify_email(payload: dict):
    """Verify email with token"""
    token = (payload or {}).get("token", "")
    email = (payload or {}).get("email", "").strip().lower()
    if not token or not email:
        raise HTTPException(status_code=400, detail="token and email are required")

    txt = await _get_text("/api/auth/verify", {"token": token, "email": email})
    
    return JSONResponse({"status": True, "message": txt or "Email verified successfully"})


############################
# SignOut
############################

@router.get("/signout")
async def signout(response: Response):
    """Sign out user"""
    response.delete_cookie("token", path="/")
    return {"status": True}