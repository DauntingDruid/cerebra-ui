import httpx
from typing import Dict, Any
import time

async def make_request_with_retry(url: str, method: str = "GET", json: Dict[str, Any] = None, headers: Dict[str, str] = None, retries: int = 3, backoff: int = 1) -> httpx.Response:
    """Make an HTTP request with retries."""
    async with httpx.AsyncClient() as client:
        for attempt in range(retries):
            try:
                if method.upper() == "POST":
                    resp = await client.post(url, json=json, headers=headers)
                else:
                    resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                if attempt == retries - 1:
                    raise e
                time.sleep(backoff * (2 ** attempt))  # Exponential backoff

# Add other utilities as needed, e.g., encryption for API keys
def encrypt_value(value: str) -> str:
    # Simple base64 for demo; use proper encryption (e.g., Fernet) in production
    return base64.b64encode(value.encode()).decode()