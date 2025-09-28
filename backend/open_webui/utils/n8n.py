import requests
from fastapi import HTTPException

def list_n8n_workflows(api_key: str, base_url: str = "http://n8n:5678") -> dict:
    """
    List available n8n workflows using the API key.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(f"{base_url}/api/v1/workflows", headers=headers)
    if response.ok:
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=f"n8n error: {response.text}")

def run_n8n_workflow(api_key: str, workflow_id: str, payload: dict, base_url: str = "http://n8n:5678") -> dict:
    """
    Run a specific n8n workflow with payload and return the output.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.post(f"{base_url}/api/v1/workflows/{workflow_id}/execute", json=payload, headers=headers)
    if response.ok:
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=f"n8n error: {response.text}")