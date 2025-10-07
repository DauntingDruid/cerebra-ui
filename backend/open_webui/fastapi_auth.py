# backend/fastapi_auth.py
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx  # Fast, async HTTP client

security = HTTPBearer(auto_error=True)


BETTERAUTH_URL = os.getenv("BETTERAUTH_URL", os.getenv("BETTERAUTH_BASE_URL", "http://betterauth-service-betterauth-1:4000")).rstrip("/")

async def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verifies the incoming Bearer token by calling BetterAuth /api/auth/me.
    Returns a dict like {email, name?, role?} if valid.
    Raises 401 if invalid/missing.
    """
    if not BETTERAUTH_URL:
        raise HTTPException(status_code=500, detail="Auth not configured")

    bearer = token.credentials if token else None
    if not bearer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    url = f"{BETTERAUTH_URL}/api/auth/me"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {bearer}"})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Auth service unreachable: {e}")

    if resp.status_code != 200:
    
        try:
            detail = resp.json().get("detail", "Invalid token")
        except Exception:
            detail = "Invalid token"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    data = resp.json() if resp.content else {}
    user = data.get("user") or {}
    if not user.get("email"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user payload")

    
    return {
        "email": user.get("email"),
        "name": user.get("name") or "",
        "role": user.get("role") or "user",
        "id": user.get("id") or user.get("_id") or user.get("email"),
    }
