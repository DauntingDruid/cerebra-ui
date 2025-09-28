from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import requests
from cryptography.fernet import Fernet, InvalidToken  # For encryption; pip install cryptography
from os import getenv

from ...internal.db import get_db
from ...models.users import User
from ...utils.auth import get_current_user  # Assume this exists or add
from ..utils.langflow import list_langflow_flows, run_langflow_flow
from ..utils.n8n import list_n8n_workflows, run_n8n_workflow  # Assume you'll create /utils/n8n.py similar to langflow.py

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Encryption key from env for security (generate with Fernet.generate_key() and set in .env/compose)
ENCRYPTION_KEY = getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY must be set in environment variables")
fernet = Fernet(ENCRYPTION_KEY.encode())  # Ensure it's bytes

def encrypt(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()

def decrypt(data: str) -> str:
    try:
        return fernet.decrypt(data.encode()).decode()
    except InvalidToken:
        raise HTTPException(400, "Invalid encrypted data")

@router.post("/{service}/key")
def save_agent_key(service: str, key: str, db: Session = Depends(get_db), user = Depends(get_current_user)):
    if service not in ["n8n", "langflow"]:
        raise HTTPException(400, "Invalid service")
    setattr(user, f"{service}_api_key", encrypt(key))
    db.commit()
    return {"message": f"{service} key saved"}

@router.get("/{service}/test")
def test_agent_key(service: str, db: Session = Depends(get_db), user = Depends(get_current_user)):
    key = decrypt(getattr(user, f"{service}_api_key", None) or "")
    if not key:
        raise HTTPException(404, "Key not found")
    
    base_url = getenv(f"{service.upper()}_BASE_URL", f"http://{service}:5678" if service == "n8n" else f"http://{service}:7860")
    endpoint = "/api/v1/workflows" if service == "n8n" else "/api/v1/flows"
    headers = {"Authorization": f"Bearer {key}"} if service == "n8n" else {"x-api-key": key}
    
    response = requests.get(f"{base_url}{endpoint}", headers=headers)
    if response.ok:
        return {"status": "connected", "data": response.json()[:5]}  # Limit data for response size
    raise HTTPException(response.status_code, f"Invalid key or connection error: {response.text}")

# LangFlow-specific endpoints
@router.get("/langflow/flows")
def get_langflow_flows(db: Session = Depends(get_db), user = Depends(get_current_user)):
    key = decrypt(user.langflow_api_key or "")
    return list_langflow_flows(key)

@router.post("/langflow/run/{flow_id}")
def execute_langflow_flow(flow_id: str, input_value: dict, db: Session = Depends(get_db), user = Depends(get_current_user)):
    key = decrypt(user.langflow_api_key or "")
    return run_langflow_flow(key, flow_id, input_value)

# n8n-specific endpoints (symmetric to LangFlow)
@router.get("/n8n/workflows")
def get_n8n_workflows(db: Session = Depends(get_db), user = Depends(get_current_user)):
    key = decrypt(user.n8n_api_key or "")
    return list_n8n_workflows(key)

@router.post("/n8n/run/{workflow_id}")
def execute_n8n_workflow(workflow_id: str, payload: dict, db: Session = Depends(get_db), user = Depends(get_current_user)):
    key = decrypt(user.n8n_api_key or "")
    return run_n8n_workflow(key, workflow_id, payload)