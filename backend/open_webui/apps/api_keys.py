from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.models.api_key import ApiKey
from backend.models.user import User
from backend.core.database import get_db
from backend.core.auth import get_current_user

router = APIRouter(prefix="/api/api_keys", tags=["api_keys"])

class ApiKeyCreate(BaseModel):
    service: str
    key_value: str

@router.post("/create")
async def create_api_key(api_key: ApiKeyCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_api_key = ApiKey(service=api_key.service, key_value=api_key.key_value, user_id=current_user.id)
    db.add(db_api_key)
    db.commit()
    db.refresh(db_api_key)
    return {"status": "created", "id": db_api_key.id}