from __future__ import annotations

import os
import base64
import json
import time
import uuid
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from pydantic import BaseModel, Field

# Configure logging to match the desired format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s:%(name)s:%(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
        logging.FileHandler('langflow_agent_bridge.log')  # Output to a file
    ]
)
logger = logging.getLogger('root')


# -------------------- Valves --------------------

class Valves(BaseModel):
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


# -------------------- Helpers --------------------

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


# -------------------- Auto-probe file download --------------------

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
    candidates = list(dict.fromkeys(candidates))  # Remove duplicates while preserving order

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
        if safe_name:
            paths.append(path_base + '_' + safe_name)
            paths.append(path_base + '-' + safe_name)
        safe_name2 = name.replace(' ', '-')
        if safe_name2 and safe_name2 != safe_name:
            paths.append(path_base + '_' + safe_name2)
            paths.append(path_base + '-' + safe_name2)

    for p in set(paths):
        probes.append((p, 404))  # assume not exists
        try:
            path_obj = Path(p)
            if path_obj.exists():
                probes[-1] = (p, 100)  # exists, trying read
                b = path_obj.read_bytes()
                dl = (name, b, mime)
                probes[-1] = (p, 200)
                break
        except Exception:
            probes[-1] = (p, -1)

    return dl, probes


# -------------------- Normalize to Langflow file dict --------------------

def _normalize_item_to_langflow_file(item: Any, valves: Valves, body: Dict[str, Any],
                                     found_meta: List[str], probe_meta: List[Tuple[str, int]]) -> Optional[Dict[str, Any]]:
    # string path
    if isinstance(item, str) and _looks_like_path(item) and _safe_path_exists(item):
        name, b = _read_path_to_base64(item) or (None, None)
        if b is None: return None
        return {
            "name": name or Path(item).name,
            "mime_type": "application/octet-stream",
            "encoding": "base64",
            "content": base64.b64encode(b).decode("ascii"),
        }
    if not isinstance(item, dict): return None

    name = item.get("name") or item.get("filename") or "file"
    mime = item.get("type") or item.get("mime_type") or "application/octet-stream"

    # path -> base64
    p = item.get("path")
    if p and _looks_like_path(p) and _safe_path_exists(p):
        name2, b = _read_path_to_base64(p) or (None, None)
        if b is not None:
            return {
                "name": name2 or name,
                "mime_type": mime,
                "encoding": "base64",
                "content": base64.b64encode(b).decode("ascii"),
            }

    # inline content
    if item.get("content"):
        out = {"name": name, "mime_type": mime, "content": item["content"]}
        if item.get("encoding"): out["encoding"] = item["encoding"]
        return out

    # base64 in `data`
    if item.get("data"):
        return {
            "name": name,
            "mime_type": mime,
            "encoding": item.get("encoding") or "base64",
            "content": item["data"],
        }

    # remote URL
    if item.get("url"):
        return {"name": name, "mime_type": mime, "url": item["url"]}

    # id-only -> auto-probe & download or disk read
    file_id = item.get("id")
    if file_id:
        dl, probes = _download_file_by_id(str(file_id), valves, body, name=name)
        probe_meta.extend(probes)
        if dl:
            dl_name, blob, dl_mime = dl
            found_meta.append("downloaded_by_id")
            return {
                "name": dl_name or name,
                "mime_type": dl_mime or mime,
                "encoding": "base64",
                "content": base64.b64encode(blob).decode("ascii"),
            }
    return None


def _walk_for_files(obj: Any, valves: Valves, body: Dict[str, Any],
                    found_meta: List[str], probe_meta: List[Tuple[str, int]],
                    parent_key: str | None = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in LIKELY_FILE_KEYS:
                container = v if isinstance(v, list) else [v]
                for it in container:
                    f = _normalize_item_to_langflow_file(it, valves, body, found_meta, probe_meta)
                    if f: found_meta.append(f"key:{k}"); out.append(f)

            if k == "messages" and isinstance(v, list):
                for i, m in enumerate(v):
                    if isinstance(m, dict):
                        for kk in ("files", "attachments", "images", "documents"):
                            if kk in m:
                                container2 = m[kk] if isinstance(m[kk], list) else [m[kk]]
                                for it in container2:
                                    f = _normalize_item_to_langflow_file(it, valves, body, found_meta, probe_meta)
                                    if f: found_meta.append(f"messages[{i}].{kk}"); out.append(f)

            child = _walk_for_files(v, valves, body, found_meta, probe_meta, parent_key=k)
            if child: out.extend(child)

        # Check if the dictionary represents a file, but only if it has meaningful file content
        if any(x in obj for x in LIKELY_ITEM_KEYS):
            if any(k in obj for k in ("path", "content", "url", "data", "id")):  # Require at least one content-related key
                f = _normalize_item_to_langflow_file(obj, valves, body, found_meta, probe_meta)
                if f: found_meta.append("inline_item"); out.append(f)

    elif isinstance(obj, list):
        for it in obj:
            child = _walk_for_files(it, valves, body, found_meta, probe_meta, parent_key=parent_key)
            if child: out.extend(child)

    elif isinstance(obj, str):
        if parent_key in LIKELY_FILE_KEYS and _looks_like_path(obj) and _safe_path_exists(obj):
            f = _normalize_item_to_langflow_file(obj, valves, body, found_meta, probe_meta)
            if f: found_meta.append(f"string_path under {parent_key}"); out.append(f)

    return out


# -------------------- Langflow call --------------------

_LAST_DOC_ID: Optional[str] = None  # process-local cache (optional)

def _last_user_message(body: Dict[str, Any]) -> str:
    msgs = body.get("messages")
    if isinstance(msgs, list) and msgs:
        for m in reversed(msgs):
            c = m.get("content")
            if c:
                if isinstance(c, str): return c
                try:
                    if isinstance(c, list):
                        for part in c:
                            if isinstance(part, dict) and part.get("text"):
                                return str(part["text"])
                    return json.dumps(c, ensure_ascii=False)
                except Exception:
                    return str(c)
        return str(msgs[-1].get("content") or "")
    return str(body.get("input") or "")

def _collect_chat_history(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(body.get("chat_history"), list): return body["chat_history"]
    if isinstance(body.get("messages"), list): return body["messages"]
    return []

def _headers_langflow(api_key: Optional[str]) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if api_key: h["x-api-key"] = api_key
    return h

def _make_payload(user_text: str, body: Dict[str, Any], valves: Valves,
                  found_meta: List[str], probe_meta: List[Tuple[str, int]]) -> Dict[str, Any]:
    global _LAST_DOC_ID

    payload: Dict[str, Any] = {
        "input_value": user_text or "",
        "input_type": "chat",
        "output_type": "chat",
        "stream": bool(body.get("stream", False)),
        "chat_history": _collect_chat_history(body),
    }

    files = _walk_for_files(body, valves, body, found_meta, probe_meta)
    if files:
        # attach files
        # de-dup
        dedup, seen = [], set()
        for f in files:
            sig = (f.get("name"), (f.get("content") or f.get("url") or "")[:32])
            if sig not in seen:
                seen.add(sig); dedup.append(f)
        payload["files"] = dedup

        # generate a fresh doc_id for THIS upload
        base_name = (dedup[0].get("name") or "doc").split(".")[0]
        new_doc_id = f"{base_name}-{uuid.uuid4().hex[:8]}-{int(time.time())}"
        payload.setdefault("variables", {})["doc_id"] = new_doc_id
        if valves.REMEMBER_LAST_DOC:
            _LAST_DOC_ID = new_doc_id
    else:
        # No files: optionally reuse last doc_id so follow-up questions hit the same doc
        if valves.REMEMBER_LAST_DOC and _LAST_DOC_ID:
            payload.setdefault("variables", {})["doc_id"] = _LAST_DOC_ID

    return payload

def _post_to_langflow(base_url: str, flow_id: str, user_api_key: Optional[str],
                      env_api_key: str, user_text: str, body: Dict[str, Any], valves: Valves,
                      timeout: int = 180) -> Dict[str, Any]:
    logger.info(f"Resolved URL: {base_url.rstrip('/')}/api/v1/run/{flow_id}")
    # Log the API keys for debugging (masked for security)
    logger.info(f"user_api_key: {user_api_key[:5] + '...' + user_api_key[-5:] if user_api_key else 'None'}")
    logger.info(f"env_api_key: {env_api_key[:5] + '...' + env_api_key[-5:] if env_api_key else 'None'}")
    # Validate the user-provided API key against the environment variable
    if env_api_key and (not user_api_key or user_api_key != env_api_key):
        logger.warning("Invalid or mismatched API key provided")
        return {"status": "error", "message": "401 Unauthorized"}

    url = f"{base_url.rstrip('/')}/api/v1/run/{flow_id}"
    found_meta: List[str] = []
    probe_meta: List[Tuple[str, int]] = []
    payload = _make_payload(user_text, body, valves, found_meta, probe_meta)
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


# ---------- Normalize reply ----------
_PREF = ("text","answer","message","output","value","result","content")
def _normalize_reply(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("status") == "error":
            return result.get("message", "Error")
        elif result.get("error"):
            found = result.get("found") or []
            probes = result.get("probes") or []
            probe_lines = "\n".join([f"- {u} -> {code}" for (u, code) in probes]) if debug and probes else ""
            info = (f"\n[Bridge found files in: {', '.join(found)}]" if found else "\n[Bridge found NO files]") + (("\n[Probe results]\n" + probe_lines) if probe_lines else "")
            detail = result.get("detail")
            pretty = (json.dumps(detail, ensure_ascii=False, indent=2)
                      if isinstance(detail, (dict, list)) else str(detail) if detail else "")
            return f"Langflow error: {result['error']}{info}\n{pretty}".strip()
        else:
            return _extract_text_from_langflow(result)
    return str(result)


# -------------------- Pipeline --------------------

class Pipeline:
    def __init__(self):
        logger.info("Langflow Agent Bridge")
        self.valves = Valves()
        if not self.valves.LANGFLOW_BASE_URL:
            logger.warning("LANGFLOW_BASE_URL is not set, requests will fail")
        if not self.valves.LANGFLOW_FLOW_ID:
            logger.warning("LANGFLOW_FLOW_ID is not set, requests will fail")
        self.env_langflow_api_key = os.getenv("LANGFLOW_API_KEY", "")  # Store the env key for validation
        if not self.env_langflow_api_key:
            logger.warning("LANGFLOW_API_KEY is not set in environment, authentication may fail")

    def _resolve_valves(self, **kwargs) -> Valves:
        v = kwargs.get("VALVES")
        if isinstance(v, dict):
            try: return Valves(**v)
            except Exception: pass
        return self.valves

    def pipe(self, body: Dict[str, Any], **kwargs) -> Any:
        valves = self._resolve_valves(**kwargs)
        base_url = valves.LANGFLOW_BASE_URL
        flow_id  = valves.LANGFLOW_FLOW_ID
        user_api_key  = valves.LANGFLOW_API_KEY
        env_api_key = self.env_langflow_api_key
        global debug
        debug    = valves.DEBUG

        if not base_url or not flow_id:
            return ("Langflow Bridge: Please configure LANGFLOW_BASE_URL and "
                    "LANGFLOW_FLOW_ID in Pipelines → Valves.")

        user_text = _last_user_message(body)
        result = _post_to_langflow(base_url, flow_id, user_api_key, env_api_key, user_text, body, valves)

        reply = _normalize_reply(result)
        return reply  # Remove debug output unless explicitly requested