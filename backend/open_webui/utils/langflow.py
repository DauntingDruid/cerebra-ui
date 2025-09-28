import requests
from fastapi import HTTPException

def list_langflow_flows(api_key: str, base_url: str = "http://langflow:7860") -> dict:
    """
    List available LangFlow flows using the API key.
    """
    headers = {"x-api-key": api_key}
    response = requests.get(f"{base_url}/api/v1/flows", headers=headers)
    if response.ok:
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=f"LangFlow error: {response.text}")

def run_langflow_flow(api_key: str, flow_id: str, input_value: dict, base_url: str = "http://langflow:7860") -> dict:
    """
    Run a specific LangFlow flow with input and return the output.
    """
    headers = {"x-api-key": api_key}
    response = requests.post(f"{base_url}/api/v1/run/{flow_id}", json=input_value, headers=headers)
    if response.ok:
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=f"LangFlow error: {response.text}")