# # backend/open_webui/routers/betterauth_adapter.py
# import os
# import json
# import psycopg
# from psycopg.rows import dict_row
# import aiohttp
# from urllib.parse import urlencode
# from sqlalchemy import text
# from open_webui.internal.db import get_db
# from fastapi import APIRouter, HTTPException, Request, Response
# from fastapi.responses import JSONResponse
# from open_webui.env import (
#     WEBUI_SESSION_COOKIE_SAME_SITE,
#     WEBUI_SESSION_COOKIE_SECURE,
# )

# DATABASE_URL = os.getenv("DATABASE_URL")

# router = APIRouter(prefix="/api/v1/auths", tags=["auths"])

# BETTERAUTH_BASE_URL = os.getenv(
#     "BETTERAUTH_BASE_URL",
#     "http://betterauth-service-betterauth-1:4000",
# ).rstrip("/")


# def _upsert_user_bootstrap(email: str, name: str):
#     """
#     Ensure a row exists in Postgres table "user".
#     - If table has 0 rows -> this email becomes admin/active.
#     - Else -> pending/user.
#     Returns (role, status, is_active).
#     """
#     with get_db() as db:
#         row = db.execute(
#             text("""SELECT role, status, is_active FROM "user" WHERE email = :e"""),
#             {"e": email},
#         ).fetchone()

#         if row:
#             return (getattr(row, "role", "user"),
#                     getattr(row, "status", "pending"),
#                     bool(getattr(row, "is_active", False)))

#         count = db.execute(text("""SELECT COUNT(*) FROM "user" """)).scalar()
#         if count == 0:
#             role, status, is_active = "admin", "active", True
#         else:
#             role, status, is_active = "user", "pending", False

#         # Upsert (create if missing)
#         db.execute(
#             text("""
#                 INSERT INTO "user" (email, name, role, status, is_active, "emailVerified")
#                 VALUES (:email, :name, :role, :status, :is_active, true)
#                 ON CONFLICT(email) DO UPDATE SET
#                     name=excluded.name,
#                     role=excluded.role,
#                     status=excluded.status,
#                     is_active=excluded.is_active
#             """),
#             {
#                 "email": email,
#                 "name": name or email.split("@")[0],
#                 "role": role,
#                 "status": status,
#                 "is_active": is_active,
#             },
#         )
#         db.commit()
#         return (role, status, is_active)
        

# def _string_error(data, fallback="Request failed"):
#     """Extract a human-readable error string from various shapes."""
#     if isinstance(data, dict):
#         for k in ("detail", "error", "message"):
#             if data.get(k):
#                 v = data[k]
#                 return v if isinstance(v, str) else json.dumps(v)
#         return json.dumps(data)
#     if isinstance(data, (list, tuple)):
#         return json.dumps(data)
#     if data is None:
#         return fallback
#     return str(data)


# async def _post_json(path: str, payload: dict):
#     if not BETTERAUTH_BASE_URL:
#         raise HTTPException(status_code=500, detail="BETTERAUTH_BASE_URL not configured")

#     url = f"{BETTERAUTH_BASE_URL}{path}"
#     timeout = aiohttp.ClientTimeout(total=15)
#     async with aiohttp.ClientSession(timeout=timeout) as s:
#         async with s.post(url, json=payload) as resp:
#             try:
#                 data = await resp.json()
#             except Exception:
#                 text = await resp.text()
#                 data = {"message": text}

#             if resp.status >= 400:
#                 raise HTTPException(
#                     status_code=resp.status,
#                     detail=_string_error(data, fallback=f"HTTP {resp.status}"),
#                 )
#             return data


# async def _get_text(path: str, query: dict):
#     """GET that may return plain text (BetterAuth verify endpoint)."""
#     if not BETTERAUTH_BASE_URL:
#         raise HTTPException(status_code=500, detail="BETTERAUTH_BASE_URL not configured")

#     qs = urlencode(query or {})
#     url = f"{BETTERAUTH_BASE_URL}{path}?{qs}"
#     timeout = aiohttp.ClientTimeout(total=15)
#     async with aiohttp.ClientSession(timeout=timeout) as s:
#         async with s.get(url) as resp:
#             txt = await resp.text()
#             if resp.status >= 400:
#                 # try to parse JSON; fall back to text
#                 try:
#                     dj = json.loads(txt)
#                     msg = _string_error(dj, txt)
#                 except Exception:
#                     msg = txt
#                 raise HTTPException(status_code=resp.status, detail=msg)
#             return txt


# def _normalize_user(u: dict, email_fallback: str = "") -> dict:
#     email = (u or {}).get("email") or email_fallback
#     name = (u or {}).get("name") or (email.split("@")[0] if email else "")
#     return {
#         "id": (u or {}).get("id") or (u or {}).get("_id") or email,
#         "email": email,
#         "name": name,
#         "role": (u or {}).get("role") or "user",
#     }


# def _json_ok_with_cookie(user: dict, token: str | None):
#     """Return {status:true, user, token} and set a JS-readable 'token' cookie."""
#     resp = JSONResponse({"status": True, "user": user, "token": token})
#     if token:
#         resp.set_cookie(
#             "token",
#             token,
#             httponly=False,  # UI reads it via JS in dev
#             samesite=WEBUI_SESSION_COOKIE_SAME_SITE,
#             secure=WEBUI_SESSION_COOKIE_SECURE,
#             path="/",
#         )
#     return resp


# # @router.post("/signin")
# # async def signin(payload: dict, request: Request):
# #     email = (payload or {}).get("email", "").strip().lower()
# #     password = (payload or {}).get("password", "")
# #     if not email or not password:
# #         raise HTTPException(status_code=400, detail="Email and password required")

# #     ba = await _post_json("/api/auth/login", {"email": email, "password": password})
# #     token = ba.get("token") or ba.get("access_token")
# #     user = _normalize_user(ba.get("user"), email_fallback=email)
# #     #user["role"] = "admin"
# #     if not token or not user.get("email"):
# #         raise HTTPException(status_code=500, detail="Login payload missing token or user")

# #     return _json_ok_with_cookie(user, token)




# @router.post("/signin")
# async def signin(payload: dict, request: Request, response: Response):
#     # Expecting { email, password } from frontend
#     email = (payload or {}).get("email", "").strip().lower()
#     password = (payload or {}).get("password", "")
#     if not email or not password:
#         raise HTTPException(status_code=400, detail="Email and password required")

#     # 1) Authenticate with BetterAuth
#     ba = await _post_json("/api/auth/login", {"email": email, "password": password})

#     token = ba.get("token") or ba.get("access_token")
#     user_raw = ba.get("user") or {}
#     if not token or not isinstance(user_raw, dict):
#         response.delete_cookie("token", path="/")
#         raise HTTPException(status_code=401, detail="Invalid credentials")

#     ret_email = (user_raw.get("email") or "").strip().lower()
#     if ret_email != email:
#         response.delete_cookie("token", path="/")
#         raise HTTPException(status_code=401, detail="Invalid credentials")

#     # Enforce email verification if BA exposes it
#     if "emailVerified" in user_raw and not bool(user_raw.get("emailVerified")):
#         response.delete_cookie("token", path="/")
#         raise HTTPException(status_code=403, detail="Email not verified")

#     # 2) Bootstrap/ensure a row in Postgres "user" (no manual DB work)
#     role, status, is_active = _upsert_user_bootstrap(email, user_raw.get("name"))

#     # 3) Block pending users until an admin approves in the frontend
#     if status != "active" or not is_active:
#         response.delete_cookie("token", path="/")
#         return JSONResponse(
#             {"status": False, "code": "PENDING_APPROVAL", "message": "Account pending admin approval"},
#             status_code=403,
#         )

#     # 4) Success → set cookie and return normalized payload
#     # Keep cookie style similar to your old route
#     response.set_cookie(
#         key="token",
#         value=token,
#         httponly=True,
#         samesite=WEBUI_SESSION_COOKIE_SAME_SITE,
#         secure=WEBUI_SESSION_COOKIE_SECURE,
#         path="/",
#     )

#     user = {
#         "id": user_raw.get("id") or user_raw.get("_id") or email,
#         "email": email,
#         "name": user_raw.get("name") or email.split("@")[0],
#         "role": role,
#         "profile_image_url": user_raw.get("profile_image_url"),
#     }

#     # If your frontend expects the old shape, return it directly:
#     return {
#         "token": token,
#         "token_type": "Bearer",
#         "expires_at": None,  # BetterAuth token expiry not surfaced here; adapt if needed
#         "id": user["id"],
#         "email": user["email"],
#         "name": user["name"],
#         "role": user["role"],
#         "profile_image_url": user["profile_image_url"],
#         "permissions": {},  # fill if you have a permissions layer
#     }


# @router.post("/signup")
# async def signup(payload: dict, request: Request):
#     name = (payload or {}).get("name") or ""
#     email = (payload or {}).get("email", "").strip().lower()
#     password = (payload or {}).get("password", "")
#     profile_image_url = (payload or {}).get("profile_image_url") or ""
#     if not email or not password:
#         raise HTTPException(status_code=400, detail="Name, email, and password required")

#     # Call BetterAuth signup
#     ba = await _post_json(
#         "/api/auth/signup",
#         {"name": name, "email": email, "password": password, "profile_image_url": profile_image_url},
#     )

#     token = ba.get("token") or ba.get("access_token")
#     user = _normalize_user(ba.get("user") or {"email": email, "name": name, "role": "user"}, email_fallback=email)

#     # Decide role/status/is_active
#     decide = _upsert_user_bootstrap(email)
#     with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
#         cur.execute(
#             '''UPDATE "user"
#                SET role = %s, status = %s, is_active = %s, updatedAt = NOW()
#              WHERE email = %s''',
#             (decide["role"], decide["status"], decide["is_active"], email)
#         )
#         conn.commit()

#     return _json_ok_with_cookie({**user, **decide}, token)


# # @router.post("/signup")
# # async def signup(payload: dict, request: Request):
# #     name = (payload or {}).get("name") or ""
# #     email = (payload or {}).get("email", "").strip().lower()
# #     password = (payload or {}).get("password", "")
# #     profile_image_url = (payload or {}).get("profile_image_url") or ""
# #     if not email or not password:
# #         raise HTTPException(status_code=400, detail="Name, email, and password required")

# #     ba = await _post_json(
# #         "/api/auth/signup",
# #         {"name": name, "email": email, "password": password, "profile_image_url": profile_image_url},
# #     )

# #     # BetterAuth may omit token until email is verified
# #     token = ba.get("token") or ba.get("access_token")
# #     user = _normalize_user(ba.get("user") or {"email": email, "name": name, "role": "user"}, email_fallback=email)
# #     #user["role"] = "admin"
# #     return _json_ok_with_cookie(user, token)


# @router.post("/send-verification")
# async def send_verification(payload: dict):
#     """
#     Body: { "email": "user@example.com" }
#     Returns: { "status": true, "message": "..."}
#     """
#     email = (payload or {}).get("email", "").strip().lower()
#     if not email:
#         raise HTTPException(status_code=400, detail="email is required")

#     await _post_json("/api/auth/request-verification", {"email": email})
#     return JSONResponse({"status": True, "message": "Verification email sent if account exists."})


# @router.post("/verify-email")
# async def verify_email(payload: dict):
#     """
#     Body: { "token": "...", "email": "user@example.com" }
#     Returns: { "status": true, "message": "..."}
#     """
#     token = (payload or {}).get("token", "")
#     email = (payload or {}).get("email", "").strip().lower()
#     if not token or not email:
#         raise HTTPException(status_code=400, detail="token and email are required")

#     txt = await _get_text("/api/auth/verify", {"token": token, "email": email})
#     return JSONResponse({"status": True, "message": txt or "Email verified"})



# @router.patch("/approve")
# async def approve_user(payload: dict):
#     email = (payload or {}).get("email", "").strip().lower()
#     if not email:
#         raise HTTPException(status_code=400, detail="Email required")

#     with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
#         cur.execute(
#             '''UPDATE "user"
#                SET status = 'active', is_active = true
#              WHERE email = %s''',
#             (email,)
#         )
#         if cur.rowcount == 0:
#             raise HTTPException(status_code=404, detail="User not found")
#         conn.commit()

#     return {"status": True, "message": f"User {email} approved"}



# @router.get("/signout")
# async def signout():
#     return JSONResponse({"status": True})





# backend/open_webui/routers/betterauth_adapter.py
import os
import json
import time
import datetime
import uuid
import aiohttp
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


def _upsert_user_bootstrap(email: str, name: str):
    """
    Ensure a row exists in Open WebUI's user table.
    Uses the existing User model from Open WebUI.
    """
    # Check if user exists using Open WebUI's Users model
    user = Users.get_user_by_email(email)
    
    if user:
        return user
    
    # User doesn't exist, determine role based on user count
    user_count = Users.get_num_users()
    role = "admin" if user_count == 0 else "user"
    
    # We don't create the user here - let the caller handle it
    # Just return the role that should be used
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
    """
    BetterAuth-integrated signin that matches the old auths.py logic exactly
    """
    
    # Handle trusted email header authentication (same as old code)
    if WEBUI_AUTH_TRUSTED_EMAIL_HEADER:
        if WEBUI_AUTH_TRUSTED_EMAIL_HEADER not in request.headers:
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_TRUSTED_HEADER)

        trusted_email = request.headers[WEBUI_AUTH_TRUSTED_EMAIL_HEADER].lower()
        trusted_name = trusted_email
        if WEBUI_AUTH_TRUSTED_NAME_HEADER:
            trusted_name = request.headers.get(
                WEBUI_AUTH_TRUSTED_NAME_HEADER, trusted_email
            )
        
        # Check if user exists in Open WebUI database
        if not Users.get_user_by_email(trusted_email.lower()):
            # Create user in both BetterAuth and Open WebUI
            await signup(
                request,
                response,
                SignupForm(
                    email=trusted_email, 
                    password=str(uuid.uuid4()), 
                    name=trusted_name
                ),
            )
        
        # Authenticate using Open WebUI's method
        user = Auths.authenticate_user_by_trusted_header(trusted_email)
    
    # Handle no-auth mode (same as old code)
    elif WEBUI_AUTH == False:
        admin_email = "admin@localhost"
        admin_password = "admin"

        if Users.get_user_by_email(admin_email.lower()):
            user = Auths.authenticate_user(admin_email.lower(), admin_password)
        else:
            if Users.get_num_users() != 0:
                raise HTTPException(400, detail=ERROR_MESSAGES.EXISTING_USERS)

            await signup(
                request,
                response,
                SignupForm(email=admin_email, password=admin_password, name="User"),
            )

            user = Auths.authenticate_user(admin_email.lower(), admin_password)
    
    # Handle BetterAuth authentication (new logic)
    else:
        email = form_data.email.lower()
        password = form_data.password
        
        # 1) Try to authenticate with BetterAuth first
        try:
            ba = await _post_json("/api/auth/login", {"email": email, "password": password})
            user_raw = ba.get("user") or {}
            
            # Check email verification in BetterAuth
            if "emailVerified" in user_raw and not bool(user_raw.get("emailVerified")):
                raise HTTPException(status_code=403, detail="Email not verified. Please check your inbox.")
        
        except HTTPException as e:
            if e.status_code == 403:
                raise
            # If BetterAuth authentication fails, raise invalid credentials
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)
        
        # 2) Get or create user in Open WebUI database using existing models
        user = Users.get_user_by_email(email)
        
        if not user:
            # User authenticated in BetterAuth but doesn't exist in Open WebUI
            # Create them using Open WebUI's Auths model
            user_count = Users.get_num_users()
            role = "admin" if user_count == 0 else request.app.state.config.DEFAULT_USER_ROLE
            
            # Create user in Open WebUI using the existing method
            hashed = get_password_hash(str(uuid.uuid4()))  # Random password since auth is via BetterAuth
            user = Auths.insert_new_auth(
                email,
                hashed,
                user_raw.get("name") or email.split("@")[0],
                user_raw.get("profile_image_url") or "/user.png",  # Default avatar
                role,
            )
            
            if not user:
                raise HTTPException(500, detail="Failed to create user in local database")

    # If we reach here, user is authenticated
    if user:
        # Generate JWT token (same as old code)
        expires_delta = parse_duration(request.app.state.config.JWT_EXPIRES_IN)
        expires_at = None
        if expires_delta:
            expires_at = int(time.time()) + int(expires_delta.total_seconds())

        token = create_token(
            data={"id": user.id},
            expires_delta=expires_delta,
        )

        datetime_expires_at = (
            datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc)
            if expires_at
            else None
        )

        # Set the cookie token (same as old code)
        response.set_cookie(
            key="token",
            value=token,
            expires=datetime_expires_at,
            httponly=True,
            samesite=WEBUI_SESSION_COOKIE_SAME_SITE,
            secure=WEBUI_SESSION_COOKIE_SECURE,
        )

        # Get user permissions (same as old code)
        user_permissions = get_permissions(
            user.id, request.app.state.config.USER_PERMISSIONS
        )

        # Return response in exact same format as old code
        return {
            "token": token,
            "token_type": "Bearer",
            "expires_at": expires_at,
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "profile_image_url": user.profile_image_url,
            "permissions": user_permissions,
        }
    else:
        raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)


############################
# SignUp with BetterAuth
############################

@router.post("/signup")
async def signup(request: Request, response: Response, form_data: SignupForm):
    """
    BetterAuth-integrated signup that matches the old auths.py logic
    """
    
    # Check if signup is allowed (same as old code)
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
    
    # Check if user already exists in Open WebUI
    if Users.get_user_by_email(email):
        raise HTTPException(400, detail=ERROR_MESSAGES.EMAIL_TAKEN)

    user_count = Users.get_num_users()
    
    # Determine role (same as old code)
    role = (
        "admin" if user_count == 0 else request.app.state.config.DEFAULT_USER_ROLE
    )

    if user_count == 0:
        # Disable signup after the first user is created
        request.app.state.config.ENABLE_SIGNUP = False

    try:
        # 1) Create user in BetterAuth
        await _post_json(
            "/api/auth/signup",
            {
                "name": form_data.name,
                "email": email,
                "password": form_data.password,
                "profile_image_url": form_data.profile_image_url or "",
            },
        )
        
        # 2) Create user in Open WebUI database
        hashed = get_password_hash(form_data.password)
        user = Auths.insert_new_auth(
            email,
            hashed,
            form_data.name,
            form_data.profile_image_url or "/user.png",  # Default avatar if not provided
            role,
        )

        if not user:
            raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)

        # Return success message - user needs to verify email before signin
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
    """
    Request password reset email
    Body: { "email": "user@example.com" }
    Returns: { "status": true, "message": "..."}
    """
    email = (payload or {}).get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    # Send password reset request to BetterAuth
    try:
        await _post_json("/api/auth/forgot-password", {"email": email, "redirectTo": "/auth/reset-password/confirm"})
        return JSONResponse({
            "status": True, 
            "message": "If an account exists with this email, a password reset link has been sent."
        })
    except HTTPException as e:
        # Always return success to prevent email enumeration
        return JSONResponse({
            "status": True, 
            "message": "If an account exists with this email, a password reset link has been sent."
        })


@router.post("/reset-password")
async def reset_password(payload: dict):
    """
    Reset password using token from email
    Body: { "token": "...", "password": "new_password" }
    Returns: { "status": true, "message": "..."}
    """
    token = (payload or {}).get("token", "")
    new_password = (payload or {}).get("password", "")
    
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new password are required")

    # Reset password via BetterAuth
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

    # Verify with BetterAuth
    txt = await _get_text("/api/auth/verify", {"token": token, "email": email})
    
    return JSONResponse({"status": True, "message": txt or "Email verified successfully"})


############################
# SignOut
############################

@router.get("/signout")
async def signout(response: Response):
    """Sign out user by deleting the token cookie"""
    response.delete_cookie("token", path="/")
    return {"status": True}