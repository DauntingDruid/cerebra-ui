from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.models.workflow import Workflow
from backend.models.user import User
from backend.core.database import get_db
from backend.core.auth import get_current_user

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

class WorkflowCreate(BaseModel):
    name: str
    framework: str
    config: dict

@router.post("/import")
async def import_workflow(workflow: WorkflowCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_workflow = Workflow(
        name=workflow.name,
        framework=workflow.framework,
        config=workflow.config,
        user_id=current_user.id
    )
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    return {"status": "imported", "id": db_workflow.id}