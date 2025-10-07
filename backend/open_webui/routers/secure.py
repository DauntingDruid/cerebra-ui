# backend/open_webui/routers/secure.py
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from open_webui.fastapi_auth import get_current_user  # <- updated absolute import

router = APIRouter(prefix="/api/v1/secure", tags=["secure"])

@router.get("/profile")
async def profile(current_user: dict = Depends(get_current_user)):
    return JSONResponse({
        "email": current_user.get("email"),
        "name":  current_user.get("name") or "",
        "role":  current_user.get("role") or "user",
        "id":    current_user.get("id"),
    })
