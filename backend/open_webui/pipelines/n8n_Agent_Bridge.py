# n8n_Agent_Bridge_2.py
from __future__ import annotations
import os, json, logging
from typing import Any, Dict, Optional, Union, Iterator
from pydantic import BaseModel, Field

try:
    import requests  # type: ignore
except Exception:
    requests = None

# Configure logging to match the desired format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s:%(name)s:%(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
        logging.FileHandler('n8n_agent_bridge.log')  # Output to a file
    ]
)
logger = logging.getLogger('root')

# ---------- Extract input ----------
def _extract_input(input=None, **kwargs) -> Optional[str]:
    logger.info(f"Received input: {input}")
    if isinstance(input, str) and input.strip():
        normalized_input = input.strip()
        logger.info(f"Normalizing input: {normalized_input}")
        return normalized_input
    for k in ("prompt", "text", "input"):
        v = kwargs.get(k)
        if isinstance(v, str) and v.strip():
            normalized_input = v.strip()
            logger.info(f"Normalizing input: {normalized_input}")
            return normalized_input
    messages = kwargs.get("messages")
    if isinstance(messages, list) and messages:
        for m in reversed(messages):
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                normalized_input = c.strip()
                logger.info(f"Normalizing input: {normalized_input}")
                return normalized_input
            if isinstance(c, list):
                parts = [b.get("text") for b in c if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
                if parts:
                    normalized_input = "\n".join(parts).strip()
                    logger.info(f"Normalizing input: {normalized_input}")
                    return normalized_input
    logger.info("Normalizing input: {}")
    return "{}"

# ---------- HTTP helper (requests if present, else urllib) ----------
def _post_to_n8n(url: str, payload: Dict[str, Any], user_api_key: str, env_api_key: str) -> Dict[str, Any]:
    logger.info(f"Resolved URL: {url}")
    # Validate the user-provided API key against the environment variable
    if not user_api_key or user_api_key != env_api_key:
        logger.warning("Invalid or mismatched API key provided")
        return {"status": "error", "message": "401 Unauthorized"}

    headers = {
        "Content-Type": "application/json",
        "X-N8N-API-KEY": user_api_key  # Use the user-provided key in the header
    }
    try:
        if requests:
            logger.info(f"Sending request to n8n webhook with payload: {json.dumps(payload, ensure_ascii=False)}")
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            try:
                response = r.json()
            except ValueError:
                response = {"text": r.text or "No response content"}
            logger.info(f"Webhook response - Status: {r.status_code}, Raw: {json.dumps(response, ensure_ascii=False)}")
            return response
        else:
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("X-N8N-API-KEY", user_api_key)
            with urllib.request.urlopen(req, timeout=60) as resp:
                status = resp.getcode()
                raw = resp.read().decode("utf-8", "replace")
                try:
                    response = json.loads(raw)
                except ValueError:
                    response = {"text": raw or "No response content"}
                logger.info(f"Webhook response - Status: {status}, Raw: {json.dumps(response, ensure_ascii=False)}")
                return response
    except Exception as e:
        logger.error(f"n8n request failed: {e}")
        return {"text": f"n8n request failed: {e}"}

# ---------- Normalize reply ----------
_PREF = ("text","answer","message","output","value","result","content")
def _normalize_reply(x: Any) -> str:
    try:
        if isinstance(x, list):
            parts = []
            for it in x:
                if isinstance(it, dict) and "json" in it:
                    parts.append(_normalize_reply(it["json"]))
                else:
                    parts.append(_normalize_reply(it))
            return "\n".join(p for p in parts if p)
        if isinstance(x, dict):
            if "json" in x:
                return _normalize_reply(x["json"])
            for k in _PREF:
                if k in x and x[k]:
                    return _normalize_reply(x[k])
            return json.dumps(x, ensure_ascii=False)
        return str(x)
    except Exception:
        return str(x)

# ---------- Valves shim (.model_dump() + .schema()) ----------
class _ValvesShim(dict):
    def model_dump(self):
        return dict(self)
    def schema(self):
        props: Dict[str, Any] = {}
        for key, spec in self.items():
            if isinstance(spec, dict):
                t = spec.get("type", "string")
                schema_type = "number" if t == "number" else "string"
                prop = {
                    "title": spec.get("label", key),
                    "type": schema_type,
                    "default": spec.get("value"),
                }
                if "min" in spec: prop["minimum"] = spec["min"]
                if "max" in spec: prop["maximum"] = spec["max"]
            else:
                t = "string"
                schema_type = "string"
                prop = {
                    "title": key,
                    "type": schema_type,
                    "default": spec if spec is not None else "",
                }
            props[key] = prop
        return {"title": "Valves", "type": "object", "properties": props, "required": []}

class Pipeline:
    id = "n8n_Agent_Bridge_2"
    name = "n8n Agent Bridge_2"
    description = "Bridge prompts to an n8n webhook and return its reply."
    enabled = True

    valves = _ValvesShim({
        "N8N_AGENT_WEBHOOK": {"type": "string", "label": "n8n Webhook URL", "value": "http://n8n:5678/webhook/5e5b725b-7a08-439f-8c30-49c68a384d0e"},
        "N8N_API_KEY": {"type": "string", "label": "n8n API Key", "value": ""},  # User-entered key
    })

    def __init__(self):
        logger.info(self.name)  # Log pipeline name on initialization
        if not self.valves["N8N_AGENT_WEBHOOK"]:
            logger.warning("N8N_AGENT_WEBHOOK is not set, webhook calls will fail")
        self.env_n8n_api_key = os.getenv("N8N_API_KEY", "")  # Store the env key for validation
        if not self.env_n8n_api_key:
            logger.warning("N8N_API_KEY is not set in environment, authentication may fail")

    def pipe(
        self,
        input: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Union[str, Iterator[str]]:
        stream = bool(kwargs.get("stream", False))
        user_text = _extract_input(input, **kwargs)
        if user_text == "{}":
            user_text = "{}"
        logger.info(f"Normalized result: {{'prompt': '{user_text}'}}")
        logger.info(f"Normalized data: {{'prompt': '{user_text}'}}")

        payload = {
            "prompt": user_text,  # Map to 'prompt' for n8n
            "messages": kwargs.get("messages"),
            "session_id": kwargs.get("session_id"),
            "context": context or {},
            "meta": {k: v for k, v in kwargs.items() if k not in {"messages", "prompt", "text", "input", "stream"}},
        }

        data = _post_to_n8n(self.valves["N8N_AGENT_WEBHOOK"].strip(), payload, self.valves["N8N_API_KEY"], self.env_n8n_api_key)
        reply = _normalize_reply(data)

        log_data = {
            "choices": [{"message": {"role": "assistant", "content": reply}}],
            "meta": {"status": 200, "json": True}
        }
        logger.info(f"stream:{stream}:{json.dumps(log_data, ensure_ascii=False)}")

        if stream:
            def gen():
                yield reply
            return gen()
        return reply

    async def inlet(self, body: Dict[str, Any] = None, context: Dict[str, Any] = None, *args, **kwargs) -> Dict[str, Any]:
        logger.info(f"Inlet processing body: {json.dumps(body or {}, ensure_ascii=False)}")
        return body or {}

    async def outlet(self, output: Dict[str, Any] = None, context: Dict[str, Any] = None, *args, **kwargs) -> Dict[str, Any]:
        logger.info(f"Outlet processing output: {json.dumps(output or {}, ensure_ascii=False)}")
        return output or {}