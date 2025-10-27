import aiohttp
import asyncio
from typing import Dict, Any, Optional
import logging
import os
import json

log = logging.getLogger(__name__)


# -----------------------
# Helpers
# -----------------------
def _is_running_in_container() -> bool:
    """Best-effort check."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "rt") as f:
            return "docker" in f.read() or "containerd" in f.read()
    except Exception:
        return False


def _normalize_base_url(url: Optional[str]) -> str:
    """
    - Ensures scheme is present (defaults to http://)
    - Strips trailing slashes
    - If running in Docker and url points to localhost, map to host.docker.internal
    """
    if not url:
        return ""

    url = url.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        url = f"http://{url}"

    # strip trailing slash (but keep scheme delimiter)
    if url.endswith("/"):
        url = url[:-1]

    if _is_running_in_container():
        # map localhost to host.docker.internal so the container can reach host services
        if "://localhost" in url:
            url = url.replace("://localhost", "://host.docker.internal")
        elif "://127.0.0.1" in url:
            url = url.replace("://127.0.0.1", "://host.docker.internal")

    return url


async def _parse_json_safe(response: aiohttp.ClientResponse) -> Any:
    """Parse JSON with graceful fallback to text body."""
    try:
        return await response.json()
    except Exception:
        try:
            text = await response.text()
        except Exception:
            text = ""
        return {"text": text}


class WorkflowExecutor:
    """Execute workflows on different platforms"""

    # -----------------------
    # LangFlow
    # -----------------------
    @staticmethod
    async def execute_langflow(
        endpoint_url: str,
        api_key: str,
        flow_id: str,
        input_data: Dict[str, Any],
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Execute a LangFlow workflow
        """
        try:
            base = _normalize_base_url(endpoint_url)
            if not base:
                raise ValueError("LangFlow endpoint_url is required")
            if not flow_id:
                raise ValueError("LangFlow flow_id is required")

            url = f"{base}/api/v1/run/{flow_id}"

            headers = {"Content-Type": "application/json"}
            # Authorization is optional (depends on LangFlow config)
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "input_value": input_data.get("message", ""),
                "output_type": "chat",
                "input_type": "chat",
                "tweaks": input_data.get("tweaks", {}),
                
            }
            # allow client to pass session_id for conversation threads
            if "session_id" in input_data:
                payload["session_id"] = input_data["session_id"]

            timeout_config = aiohttp.ClientTimeout(total=timeout)

            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        raise Exception(f"LangFlow API error ({response.status}): {error_text}")

                    result = await _parse_json_safe(response)
                    return {
                        "success": True,
                        "output": result,
                        "message": "Workflow executed successfully"
                    }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"LangFlow execution timed out after {timeout}s"
            }
        except Exception as e:
            log.error(f"LangFlow execution error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # -----------------------
    # n8n
    # -----------------------
    @staticmethod
    async def execute_n8n(
        endpoint_url: str,
        api_key: str,
        workflow_id: Optional[str],
        input_data: Dict[str, Any],
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Execute an n8n workflow via webhook or full URL.
        - If endpoint_url already contains a full webhook URL, we POST there.
        - Otherwise we append /{workflow_id}.
        """
        try:
            base = _normalize_base_url(endpoint_url)
            if not base:
                raise ValueError("n8n endpoint_url is required")

            # If it already looks like a full webhook URL, use as-is.
            if workflow_id:
                url = f"{base}/{workflow_id}"
            else:
                url = base  # assume user pasted the full webhook URL

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            timeout_config = aiohttp.ClientTimeout(total=timeout)

            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.post(url, json=input_data, headers=headers) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        raise Exception(f"n8n API error ({response.status}): {error_text}")

                    result = await _parse_json_safe(response)
                    return {
                        "success": True,
                        "output": result,
                        "message": "Workflow executed successfully"
                    }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"n8n execution timed out after {timeout}s"
            }
        except Exception as e:
            log.error(f"n8n execution error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # -----------------------
    # Custom HTTP
    # -----------------------
    @staticmethod
    async def execute_custom(
        endpoint_url: str,
        api_key: Optional[str],
        input_data: Dict[str, Any],
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Execute a custom API workflow
        """
        try:
            url = _normalize_base_url(endpoint_url)
            if not url:
                raise ValueError("Custom endpoint_url is required")
            # Detect Deep Research and route to proper executor
            if "deep-research" in url or ":2024" in url:
                return await WorkflowExecutor.execute_deep_research(
                    endpoint_url=endpoint_url,
                    api_key=api_key,
                    input_data=input_data,
                    timeout=timeout
                )

            request_headers = dict(headers or {})
            request_headers["Content-Type"] = "application/json"
            if api_key:
                request_headers["Authorization"] = f"Bearer {api_key}"

            timeout_config = aiohttp.ClientTimeout(total=timeout)

            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.request(
                    method,
                    url,
                    json=input_data,
                    headers=request_headers
                ) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        raise Exception(f"Custom API error ({response.status}): {error_text}")

                    result = await _parse_json_safe(response)
                    return {
                        "success": True,
                        "output": result,
                        "message": "Workflow executed successfully"
                    }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Custom execution timed out after {timeout}s"
            }
        except Exception as e:
            log.error(f"Custom execution error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # -----------------------
    # LangChain (minimal, with dry-run fallback)
    # -----------------------
    @staticmethod
    async def execute_langchain(
        api_key: Optional[str],
        input_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Minimal LangChain runner:
        - If langchain libs are installed AND api_key provided → call LLM.
        - Otherwise → dry-run that echoes back the message, so it always works.
        """
        try:
            if api_key:
                # Lazy import so code runs even if libs aren't installed yet
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_openai import ChatOpenAI

                model_name = config.get("model", "gpt-4o-mini")
                template = config.get("template", "Answer briefly: {message}")

                llm = ChatOpenAI(api_key=api_key, model=model_name)
                prompt = ChatPromptTemplate.from_template(template)
                chain = prompt | llm

                out = chain.invoke({"message": input_data.get("message", "")})
                text = getattr(out, "content", str(out))
                return {
                    "success": True,
                    "output": {"text": text},
                    "message": "LangChain completed"
                }
        except Exception as e:
            # If anything fails (no libs, invalid key, etc.), fall through to dry-run
            log.warning(f"LangChain real call failed, falling back to dry-run: {e}")

        # Dry-run fallback
        return {
            "success": True,
            "output": {"text": f"[langchain dry-run] {input_data.get('message', '')}"},
            "message": "LangChain dry-run"
        }

    # -----------------------
    # Deep Research (LangGraph)
    # -----------------------
    @staticmethod
    async def execute_deep_research(
        endpoint_url: str,
        api_key: Optional[str],
        input_data: Dict[str, Any],
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Execute Deep Research (LangGraph) workflow
        Reuses thread_id from session_id (same pattern as Langflow)
        """
        try:
            log.info(f"Deep Research input_data: {input_data}")
            base = _normalize_base_url(endpoint_url)
            if not base:
                raise ValueError("Deep Research endpoint_url is required")

            headers = {"Content-Type": "application/json"}
            timeout_config = aiohttp.ClientTimeout(total=timeout)

            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                # Step 1: Create assistant with proper config
                assistant_data = {
                    "graph_id": "Deep Researcher",
                    "name": "Research Assistant",
                    "if_exists": "do_nothing",
                    "config": {
                        "configurable": {
                            "summarization_model": "openai:gpt-4o-mini",
                            "research_model": "openai:gpt-4o",
                            "compression_model": "openai:gpt-4o",
                            "final_report_model": "openai:gpt-4o"
                        }
                    }
                }
                
                async with session.post(
                    f"{base}/assistants",
                    json=assistant_data,
                    headers=headers
                ) as resp:
                    if resp.status >= 400:
                        error_text = await resp.text()
                        log.error(f"Assistant creation failed: {error_text}")
                    assistant = await resp.json()
                    assistant_id = assistant.get("assistant_id")
                    log.info(f"Created assistant: {assistant_id}")

                # Step 2: Get or create thread (using session_id like Langflow)
                thread_id = input_data.get("session_id") or input_data.get("thread_id")
                
                if not thread_id:
                    # Create new thread only if no session_id provided
                    async with session.post(
                        f"{base}/threads",
                        json={},
                        headers=headers
                    ) as resp:
                        if resp.status >= 400:
                            error_text = await resp.text()
                            raise Exception(f"Failed to create thread: {error_text}")
                        thread = await resp.json()
                        thread_id = thread.get("thread_id")
                        log.info(f"Created NEW thread: {thread_id}")
                else:
                    log.info(f"Reusing existing thread: {thread_id}")

                # Step 3: Run research
                run_data = {
                    "assistant_id": assistant_id,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": input_data.get("message", "")
                            }
                        ]
                    },
                    "stream_mode": "values"
                }
                
                log.info(f"Starting research run for thread: {thread_id}")
                
                async with session.post(
                    f"{base}/threads/{thread_id}/runs/wait",
                    json=run_data,
                    headers=headers
                ) as resp:
                    if resp.status >= 400:
                        error_text = await resp.text()
                        raise Exception(f"Research run failed: {error_text}")
                    
                    result = await resp.json()
                    log.info(f"Research result type: {type(result)}")
                    
                    output_text = "Research completed"
                    
                    # Handle DICT response
                    if isinstance(result, dict):
                        log.info(f"Result keys: {list(result.keys())}")
                        
                        if "output" in result:
                            output_text = result["output"]
                        elif "text" in result:
                            output_text = result["text"]
                        elif "content" in result:
                            output_text = result["content"]
                        elif "messages" in result:
                            messages = result["messages"]
                            if isinstance(messages, list) and len(messages) > 0:
                                last_msg = messages[-1]
                                if isinstance(last_msg, dict):
                                    output_text = last_msg.get("content", output_text)
                        elif "values" in result:
                            values = result["values"]
                            if isinstance(values, dict) and "messages" in values:
                                messages = values["messages"]
                                if isinstance(messages, list) and len(messages) > 0:
                                    output_text = messages[-1].get("content", output_text)
                        
                        log.info(f"Extracted text length: {len(output_text)}")
                    
                    # Handle LIST response
                    elif isinstance(result, list) and len(result) > 0:
                        last_state = result[-1]
                        if isinstance(last_state, dict) and "messages" in last_state:
                            messages = last_state["messages"]
                            if isinstance(messages, list) and len(messages) > 0:
                                last_message = messages[-1]
                                if isinstance(last_message, dict):
                                    output_text = last_message.get("content", output_text)
                    
                    return {
                        "success": True,
                        "output": {
                            "outputs": [
                                {
                                    "text": output_text
                                }
                            ]
                        },
                        "session_id": thread_id,  # Return thread_id as session_id for next call
                        "message": "Deep Research completed"
                    }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Deep Research timed out after {timeout}s"
            }
        except Exception as e:
            log.error(f"Deep Research error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
# -----------------------
# Dispatcher
# -----------------------
async def execute_workflow(
    workflow_type: str,
    config: Dict[str, Any],
    api_key: Optional[str],
    input_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Main workflow execution dispatcher
    """
    executor = WorkflowExecutor()

    if workflow_type == "langflow":
        return await executor.execute_langflow(
            endpoint_url=config.get("endpoint_url"),
            api_key=api_key or "",
            flow_id=config.get("flow_id"),
            input_data=input_data,
            timeout=config.get("timeout", 300)
        )

    elif workflow_type == "n8n":
        return await executor.execute_n8n(
            endpoint_url=config.get("endpoint_url"),
            api_key=api_key or "",
            workflow_id=config.get("workflow_id"),
            input_data=input_data,
            timeout=config.get("timeout", 300)
        )

    elif workflow_type == "langchain":
        return await executor.execute_langchain(
            api_key=api_key,
            input_data=input_data,
            config=config
        )
    
    elif workflow_type == "deep_research":
        return await executor.execute_deep_research(
            endpoint_url=config.get("endpoint_url"),
            api_key=api_key,
            input_data=input_data,
            timeout=config.get("timeout", 300)
        )

    elif workflow_type == "custom":
        return await executor.execute_custom(
            endpoint_url=config.get("endpoint_url"),
            api_key=api_key,
            input_data=input_data,
            method=config.get("method", "POST"),
            headers=config.get("headers"),
            timeout=config.get("timeout", 300)
        )

    else:
        return {
            "success": False,
            "error": f"Unknown workflow type: {workflow_type}"
        }
