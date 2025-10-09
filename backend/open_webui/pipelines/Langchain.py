# merged_routing_adapter_pipeline.py (valve for chat/completions routing in Open WebUI Pipelines)
from __future__ import annotations

import os
import base64
import json
import time
import uuid
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Iterator

import requests
from pydantic import BaseModel, Field

# LangChain imports for routing
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI  # Adjust for your LLM provider if needed
from langchain_core.output_parsers import StrOutputParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s:%(name)s:%(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('merged_routing_adapter.log')
    ]
)
logger = logging.getLogger('root')

# -------------------- Valves (merged from both bridges + LangChain config) --------------------

class Valves(BaseModel):
    # Langflow settings
    LANGFLOW_BASE_URL: str = Field(
        default="http://langflow:7860",
        description="Base URL of your Langflow server (no trailing slash).",
    )
    LANGFLOW_FLOW_ID: str = Field(
        default="",
        description="Langflow Flow ID (UUID).",
    )
    LANGFLOW_API_KEY: str = Field(
        default="",
        description="Langflow API Key (sent as x-api-key).",
        json_schema_extra={"password": True},
    )
    FILE_DOWNLOAD_HEADER: str = Field(
        default="NOAUTH",
        description="Single header for file GET (or NOAUTH/none/- to skip). To download files via API, generate an API key in Open WebUI under Settings > Account, then set 'Authorization: Bearer <your_api_key>'. This is required for HTTP probes to succeed.",
        json_schema_extra={"password": True},
    )
    UPLOADS_DIR: str = Field(
        default="/app/backend/data/uploads",
        description="Directory where uploaded files are stored. To access from Pipelines container (separate from Open WebUI), share the Open WebUI data volume in docker-compose.yaml under pipelines service: volumes: - open-webui:/app/backend/data (assuming volume name 'open-webui' from Open WebUI service). Then set this to '/app/backend/data/uploads'. If using bind mount (e.g., ./open-webui:/app/backend/data in Open WebUI), use the same in pipelines. If files are not found, check docker logs or enable DEBUG to see probed paths. Alternatively, use HTTP download with proper FILE_DOWNLOAD_HEADER.",
    )
    REMEMBER_LAST_DOC: bool = Field(
        default=True,
        description="Reuse last doc_id for text-only follow-ups in this process.",
    )
    DEBUG: bool = Field(
        default=False,
        description="If true, include probe info and where files were forwarded.",
    )

    # n8n settings
    N8N_AGENT_WEBHOOK: str = Field(
        default="http://n8n:5678/webhook/5e5b725b-7a08-439f-8c30-49c68a384d0e",
        description="n8n Webhook URL.",
    )
    N8N_API_KEY: str = Field(
        default="",
        description="n8n API Key.",
        json_schema_extra={"password": True},
    )

    # LangChain classification settings
    CLASSIFICATION_MODEL: str = Field(
        default="gpt-4o-mini",
        description="LLM model for intent classification.",
    )
    OPENAI_API_KEY: str = Field(
        default="",
        description="API key for the classification LLM (e.g., OpenAI).",
        json_schema_extra={"password": True},
    )

# -------------------- Helpers from Langflow Bridge --------------------

LIKELY_FILE_KEYS = {
    "attachments", "files", "images", "documents", "uploaded", "uploads",
    "uploaded_files", "upload_file_paths", "file_paths",
}
LIKELY_ITEM_KEYS = {
    "path", "content", "url", "data", "name", "filename", "type", "mime_type", "encoding", "id"
}

def _looks_like_path(s: str) -> bool:
    if not isinstance(s, str): return False
    if "\n" in s or "\r" in s: return False
    if len(s) > 512: return False
    if s.startswith(("/", "./", "../")): return True
    if (":" in s and "\\" in s) or s.startswith("\\"): return True  # Windows-ish
    return ("/" in s or "\\" in s)

def _safe_path_exists(p: str) -> bool:
    try: return Path(p).exists()
    except Exception: return False

def _read_path_to_base64(p: str) -> Optional[Tuple[str, bytes]]:
    try:
        b = Path(p).read_bytes()
        return (Path(p).name, b)
    except Exception:
        return None

def _parse_single_header(header_str: str) -> Dict[str, str]:
    if not header_str or ":" not in header_str:  # NOAUTH/none/- are ignored
        return {}
    k, v = header_str.split(":", 1)
    return {k.strip(): v.strip()}

# -------------------- Auto-probe file download from Langflow Bridge --------------------

def _infer_webui_bases(body: Dict[str, Any]) -> List[str]:
    bases: List[str] = []
    for env_key in ("OPENWEBUI_BASE_URL", "OPENWEBUI_INTERNAL_URL", "WEBUI_BASE_URL"):
        v = os.getenv(env_key)
        if v:
            bases.append(v.rstrip("/"))
    for key in ("origin", "base_url", "webui_base_url"):
        v = body.get(key)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            bases.append(v.rstrip("/"))
    bases += [
        "http://open-webui:8080",  # Prioritize known working URL
        "http://openwebui:8080",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    # de-dup
    seen, uniq = set(), []
    for b in bases:
        if b not in seen:
            seen.add(b); uniq.append(b)
    return uniq

def _download_file_by_id(file_id: str, valves: Valves, body: Dict[str, Any], name: str = "file") -> Tuple[Optional[Tuple[str, bytes, str]], List[Tuple[str, int]]]:
    probes: List[Tuple[str, int]] = []
    headers = _parse_single_header(valves.FILE_DOWNLOAD_HEADER)
    candidates = []
    for base in _infer_webui_bases(body):
        base = base.rstrip("/")
        candidates += [
            f"{base}/api/files/{{id}}",  # Prioritize known working endpoint
            f"{base}/api/files/{{id}}/raw",
            f"{base}/api/files/{{id}}/download",
            f"{base}/api/v1/files/{{id}}",
            f"{base}/api/v1/files/{{id}}/content",
            f"{base}/files/{{id}}",
        ]
    candidates = list(dict.fromkeys(candidates))

    for tmpl in candidates:
        url = tmpl.replace("{id}", file_id)
        try:
            r = requests.get(url, headers=headers, timeout=60)
            probes.append((url, r.status_code))
            if r.status_code == 200:
                mime = r.headers.get("Content-Type") or "application/octet-stream"
                cd = r.headers.get("Content-Disposition") or ""
                if "filename=" in cd:
                    name = cd.split("filename=", 1)[1].strip().strip('"').strip("'")
                return (name, r.content, mime), probes
        except Exception:
            probes.append((url, -1))

    # If HTTP fails, try reading from disk
    dl: Optional[Tuple[str, bytes, str]] = None
    mime = "application/octet-stream"
    path_base = f"{valves.UPLOADS_DIR.rstrip('/')}/{file_id}"
    paths = [path_base]
    if name:
        ext = Path(name).suffix
        if ext:
            paths.append(path_base + ext)
        safe_name = name.replace(' ', '_')
        if safe_name != name:
            paths.append(path_base + Path(safe_name).suffix)
    for p in paths:
        if _safe_path_exists(p):
            dl = _read_path_to_base64(p)
            if dl:
                return (dl[0], dl[1], mime), probes
    return None, probes

def _find_files(body: Dict[str, Any], valves: Valves) -> List[Dict[str, str]]:
    files = []
    for k in LIKELY_FILE_KEYS:
        v = body.get(k)
        if isinstance(v, list) and v:
            for item in v:
                if not isinstance(item, dict):
                    continue
                file_id = None
                for ik in LIKELY_ITEM_KEYS:
                    iv = item.get(ik)
                    if isinstance(iv, str) and iv.strip():
                        if _looks_like_path(iv):
                            if _safe_path_exists(iv):
                                dl = _read_path_to_base64(iv)
                                if dl:
                                    files.append({
                                        "data_type": "file",
                                        "data": base64.b64encode(dl[1]).decode("ascii"),
                                        "filename": dl[0],
                                    })
                                    break
                        elif len(iv) == 36 and "-" in iv:  # UUID-like
                            file_id = iv
                if file_id:
                    dl, probes = _download_file_by_id(file_id, valves, body, item.get("filename", ""))
                    if dl:
                        files.append({
                            "data_type": "file",
                            "data": base64.b64encode(dl[1]).decode("ascii"),
                            "filename": dl[0],
                        })
    return files

# -------------------- Post to Langflow --------------------

def _headers_langflow(api_key: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    return headers

def _post_to_langflow(base_url: str, flow_id: str, user_api_key: str, env_api_key: str, user_text: str, body: Dict[str, Any], valves: Valves, timeout: int = 120) -> Dict[str, Any]:
    # Check API key
    if env_api_key and (not user_api_key or user_api_key != env_api_key):
        return {"status": "error", "message": "401 Unauthorized due to missing or wrong Langflow API key."}

    url = f"{base_url.rstrip('/')}/api/v1/run/{flow_id}"
    found_meta: List[str] = []
    probe_meta: List[Tuple[str, int]] = []
    payload = {
        "input_value": user_text,
        "files": _find_files(body, valves),
    }
    try:
        logger.info(f"Sending request to Langflow with payload: {json.dumps(payload, ensure_ascii=False)}")
        resp = requests.post(url, json=payload, headers=_headers_langflow(user_api_key), timeout=timeout)
        logger.info(f"Langflow response - Status: {resp.status_code}, Raw: {resp.text}")
    except requests.RequestException as e:
        logger.error(f"Langflow request failed: {e}")
        return {"error": f"Langflow request failed: {e}", "found": found_meta, "probes": probe_meta, "payload": payload}

    if not resp.ok:
        try:
            j = resp.json(); detail = j.get("detail", j)
        except Exception:
            detail = resp.text
        return {
            "error": f"Langflow returned {resp.status_code} {resp.reason}",
            "url": url,
            "detail": detail,
            "found": found_meta,
            "probes": probe_meta,
            "payload": payload,
        }

    try:
        result = resp.json()
    except Exception:
        return {"error": "Invalid JSON from Langflow", "text": resp.text, "found": found_meta, "probes": probe_meta}

    result["_bridge_found"] = found_meta
    result["_bridge_probes"] = probe_meta
    return result

def _extract_text_from_langflow(result: dict) -> str:
    texts = []
    try:
        for out in result.get("outputs", []) or []:
            inner = out.get("outputs", []) or []
            for item in inner:
                res = item.get("results")
                if isinstance(res, dict):
                    msg = res.get("message")
                    if isinstance(msg, dict):
                        data = msg.get("data")
                        if isinstance(data, dict):
                            t = data.get("text")
                            if isinstance(t, str) and t.strip(): texts.append(t.strip())
                        if not texts:
                            t = msg.get("message") or msg.get("text")
                            if isinstance(t, str) and t.strip(): texts.append(t.strip())
                elif isinstance(res, list) and res:
                    t = res[0].get("text") if isinstance(res[0], dict) else None
                    if isinstance(t, str) and t.strip(): texts.append(t.strip())
    except Exception:
        pass
    if not texts:
        t = result.get("text")
        if isinstance(t, str) and t.strip(): texts.append(t.strip())
    if not texts:
        art = result.get("artifacts") or {}
        t = art.get("message")
        if isinstance(t, str) and t.strip(): texts.append(t.strip())
    if not texts:
        msgs = result.get("messages")
        if isinstance(msgs, list):
            for m in reversed(msgs):
                t = m.get("message") if isinstance(m, dict) else None
                if isinstance(t, str) and t.strip():
                    texts.append(t.strip()); break
    if not texts:
        try: return json.dumps(result, ensure_ascii=False, separators=(",", ":"))[:4000]
        except Exception: return str(result)[:4000]
    return "\n\n".join(texts)

# ---------- Normalize reply (merged from both) ----------
_PREF = ("text", "answer", "message", "output", "value", "result", "content", "response")

def _normalize_reply(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("status") == "error":
            return result.get("message", "Error")
        elif result.get("error"):
            return f"Error: {result['error']}"
        elif "outputs" in result:
            return _extract_text_from_langflow(result)
        else:
            for key in _PREF:
                v = result.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
                elif isinstance(v, (dict, list)):
                    # Recurse if nested
                    nested = _normalize_reply(v)
                    if nested.strip():
                        return nested.strip()
            return json.dumps(result, ensure_ascii=False)  # Fallback to clean JSON string
    elif isinstance(result, list) and result:
        return _normalize_reply(result[0])  # Assume first item
    return str(result)

# ---------- Extract input (from n8n bridge) ----------
def _extract_input(body: Dict[str, Any]) -> Optional[str]:
    for k in ("prompt", "text", "input"):
        v = body.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        for m in reversed(messages):
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                return c.strip()
            if isinstance(c, list):
                parts = [b.get("text") for b in c if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
                if parts:
                    return "\n".join(parts).strip()
    return "{}"

# ---------- HTTP helper (from n8n bridge) ----------
def _post_to_n8n(url: str, payload: Dict[str, Any], user_api_key: str, env_api_key: str) -> Dict[str, Any]:
    if not user_api_key or user_api_key != env_api_key:
        return {"status": "error", "message": "401 Unauthorized due to missing or wrong n8n API key."}

    headers = {
        "Content-Type": "application/json",
        "X-N8N-API-KEY": user_api_key
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": f"n8n request failed: {e}"}

# -------------------- Pipeline Class (merged with LangChain routing) --------------------

class Pipeline:
    id = "Merged_Routing_Adapter"
    name = "Merged Routing Adapter"
    description = "Routes prompts to Langflow (research) or n8n (general) using LangChain classification."
    enabled = True

    valves = Valves()

    def __init__(self):
        logger.info(self.name)
        if not self.valves.LANGFLOW_BASE_URL or not self.valves.LANGFLOW_FLOW_ID:
            logger.warning("Langflow settings incomplete")
        if not self.valves.N8N_AGENT_WEBHOOK:
            logger.warning("n8n webhook not set")
        self.env_langflow_api_key = os.getenv("LANGFLOW_API_KEY", "")
        self.env_n8n_api_key = os.getenv("N8N_API_KEY", "")
        self.env_openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.llm = ChatOpenAI(model=self.valves.CLASSIFICATION_MODEL, api_key=self.valves.OPENAI_API_KEY)
        self.prompt = ChatPromptTemplate.from_template(
            "Classify as 'research' only if the query is about an academic research topic (e.g., scientific studies, scholarly articles, theoretical analysis in fields like physics, history, or biology), otherwise 'general': {query}\nOutput: research or general"
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def inlet(self, body: Dict[str, Any] = None, context: Dict[str, Any] = None, *args, **kwargs) -> Dict[str, Any]:
        logger.info(f"Inlet processing body: {json.dumps(body or {}, ensure_ascii=False)}")
        return body or {}

    async def outlet(self, output: Dict[str, Any] = None, context: Dict[str, Any] = None, *args, **kwargs) -> Dict[str, Any]:
        logger.info(f"Outlet processing output: {json.dumps(output or {}, ensure_ascii=False)}")
        return output or {}

    def pipe(self, body: Dict[str, Any], **kwargs) -> str:
        user_text = _extract_input(body)
        if not user_text:
            return "No input provided"
            
        if self.env_openai_api_key and (not self.valves.OPENAI_API_KEY or self.valves.OPENAI_API_KEY != self.env_openai_api_key):
            return "401 Unauthorized due to missing or wrong OpenAI API key."

        # LangChain classification
        classification = self.chain.invoke({"query": user_text})
        is_research = "research" in classification.lower()

        if is_research:
            # Route to Langflow (using Langflow bridge logic)
            result = _post_to_langflow(
                self.valves.LANGFLOW_BASE_URL, self.valves.LANGFLOW_FLOW_ID,
                self.valves.LANGFLOW_API_KEY, self.env_langflow_api_key,
                user_text, body, self.valves
            )
        else:
            # Route to n8n (using n8n bridge logic)
            payload = {"prompt": user_text, "messages": body.get("messages", [])}
            result = _post_to_n8n(
                self.valves.N8N_AGENT_WEBHOOK, payload,
                self.valves.N8N_API_KEY, self.env_n8n_api_key
            )

        return _normalize_reply(result)
