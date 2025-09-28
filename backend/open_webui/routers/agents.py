from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict

from ...internal.db import get_db
from ...models.agents import Agent
from ...utils.auth import get_current_user  # Assume this exists

router = APIRouter(prefix="/agents", tags=["agents"])

@router.post("/save-agent")
def save_agent(graph: Dict, db: Session = Depends(get_db), user = Depends(get_current_user)):
    agent = Agent(user_id=user.id, graph=graph)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return {"id": agent.id}

@router.get("/list", response_model=List[Dict])
def list_agents(db: Session = Depends(get_db), user = Depends(get_current_user)):
    agents = db.query(Agent).filter(Agent.user_id == user.id).all()
    if not agents:
        raise HTTPException(404, "No agents found")
    return [{"id": a.id, "graph": a.graph} for a in agents]