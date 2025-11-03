from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional, Dict, Any
import asyncio
import logging
import json
from urllib.parse import urlparse, urlunparse

from open_webui.models.workflows import (
    Workflows,
    WorkflowCredentials,
    WorkflowExecutions,
    WorkflowModel,
    WorkflowForm,
    WorkflowCredentialModel,
    WorkflowCredentialForm,
    WorkflowExecutionModel,
    WorkflowExecutionForm,
)
from open_webui.utils.auth import get_verified_user
from open_webui.models.users import UserModel

router = APIRouter()
log = logging.getLogger(__name__)


def _norm(s: Optional[str]) -> str:
    """Lowercase + strip for consistent matching."""
    return (s or "").strip().lower()


def _fix_endpoint_for_container(endpoint_url: Optional[str]) -> Optional[str]:
    """
    If backend runs in Docker: 'http://localhost:7860' from UI will not resolve.
    Rewrite to 'http://host.docker.internal:7860' so container can reach host.
    """
    if not endpoint_url:
        return endpoint_url
    try:
        p = urlparse(endpoint_url)
        if p.hostname in {"localhost", "127.0.0.1"}:
            new_netloc = f"host.docker.internal:{p.port}" if p.port else "host.docker.internal"
            p = p._replace(netloc=new_netloc)
            return urlunparse(p)
        return endpoint_url
    except Exception:
        return endpoint_url


####################
# Workflow Endpoints
####################

@router.get("/", response_model=List[WorkflowModel])
async def get_workflows(user: UserModel = Depends(get_verified_user)):
    """Get all workflows for the current user"""
    return Workflows.get_workflows_by_user_id(user.id)


@router.get("/{workflow_id}", response_model=WorkflowModel)
async def get_workflow(workflow_id: str, user: UserModel = Depends(get_verified_user)):
    """Get a specific workflow by ID"""
    workflow = Workflows.get_workflow_by_id(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    # Check if user owns this workflow
    if workflow.user_id != user.id and getattr(user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    return workflow


@router.post("/", response_model=WorkflowModel)
async def create_workflow(
    form_data: WorkflowForm,
    user: UserModel = Depends(get_verified_user)
):
    """Create a new workflow"""
    # normalize type and fix endpoint for container if present
    form_data.workflow_type = _norm(form_data.workflow_type)
    cfg = dict(form_data.config or {})
    if "endpoint_url" in cfg:
        cfg["endpoint_url"] = _fix_endpoint_for_container(cfg.get("endpoint_url"))
    form_data.config = cfg

    workflow = Workflows.create_workflow(user.id, form_data)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workflow"
        )

    return workflow


@router.put("/{workflow_id}", response_model=WorkflowModel)
async def update_workflow(
    workflow_id: str,
    form_data: WorkflowForm,
    user: UserModel = Depends(get_verified_user)
):
    """Update an existing workflow"""
    existing_workflow = Workflows.get_workflow_by_id(workflow_id)

    if not existing_workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    # Check ownership
    if existing_workflow.user_id != user.id and getattr(user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # normalize + endpoint fix
    form_data.workflow_type = _norm(form_data.workflow_type)
    cfg = dict(form_data.config or {})
    if "endpoint_url" in cfg:
        cfg["endpoint_url"] = _fix_endpoint_for_container(cfg.get("endpoint_url"))
    form_data.config = cfg

    workflow = Workflows.update_workflow(workflow_id, form_data)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update workflow"
        )

    return workflow


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    user: UserModel = Depends(get_verified_user)
):
    """Delete a workflow"""
    existing_workflow = Workflows.get_workflow_by_id(workflow_id)

    if not existing_workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    # Check ownership
    if existing_workflow.user_id != user.id and getattr(user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    success = Workflows.delete_workflow(workflow_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete workflow"
        )

    return {"status": True, "message": "Workflow deleted successfully"}


####################
# Credential Endpoints
####################

@router.get("/credentials/list", response_model=List[WorkflowCredentialModel])
async def get_credentials(user: UserModel = Depends(get_verified_user)):
    """Get all credentials for the current user (API keys are NOT returned)"""
    credentials = WorkflowCredentials.get_credentials_by_user_id(user.id)
    return credentials


@router.post("/credentials", response_model=WorkflowCredentialModel)
async def create_credential(
    form_data: WorkflowCredentialForm,
    user: UserModel = Depends(get_verified_user)
):
    """Store a new API credential"""
    form_data.service_name = _norm(form_data.service_name)

    # Validate api_key is provided for creation
    if not form_data.api_key or not form_data.api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is required when creating a credential"
        )

    # Fix endpoint for container if provided
    if form_data.endpoint_url:
        form_data.endpoint_url = _fix_endpoint_for_container(form_data.endpoint_url)

    credential = WorkflowCredentials.create_credential(user.id, form_data)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create credential. Service name might already exist."
        )

    return credential


@router.put("/credentials/{credential_id}", response_model=WorkflowCredentialModel)
async def update_credential(
    credential_id: str,
    form_data: WorkflowCredentialForm,
    user: UserModel = Depends(get_verified_user)
):
    """Update an existing credential"""
    existing_credential = WorkflowCredentials.get_credentials_by_user_id(user.id)
    
    # Check if credential exists
    cred_exists = any(c.id == credential_id for c in existing_credential)
    if not cred_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )

    form_data.service_name = _norm(form_data.service_name)
    if form_data.endpoint_url:
        form_data.endpoint_url = _fix_endpoint_for_container(form_data.endpoint_url)

    credential = WorkflowCredentials.update_credential(credential_id, user.id, form_data)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update credential"
        )

    return credential


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: str,
    user: UserModel = Depends(get_verified_user)
):
    """Delete a credential"""
    success = WorkflowCredentials.delete_credential(credential_id, user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )

    return {"status": True, "message": "Credential deleted successfully"}


####################
# Execution Endpoints (NON-BLOCKING)
####################

@router.post("/{workflow_id}/execute")
async def execute_workflow_endpoint(
    workflow_id: str,
    request: Request,
    user: UserModel = Depends(get_verified_user)
):
    """
    Fire-and-return execution:
      1) Create execution row as 'pending'
      2) Spawn background task
      3) Return immediately with {"id": ..., "status": "pending"}
    Keeps UI responsive even if external services are slow.
    """
    # Verify workflow
    workflow = Workflows.get_workflow_by_id(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    if workflow.user_id != user.id and getattr(user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    if not workflow.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow is not active"
        )

    # Get body (optional)
    try:
        body = await request.json()
    except Exception:
        body = {}

    input_data = body.get("input_data") or {"message": ""}

    # ============================================================
    # ADD SESSION_ID FOR DEEP_RESEARCH (THREAD CONTINUITY)
    # ============================================================
    service_name = _norm(workflow.workflow_type)
    
    if service_name == "deep_research" and body.get("chat_id"):
        # Get the last successful execution for this workflow + chat
        last_execution = WorkflowExecutions.get_last_completed_execution(
            workflow_id=workflow_id,
            chat_id=body.get("chat_id")
        )
        
        # Extract session_id from previous execution's output
        if last_execution and last_execution.output_data:
            try:
                if isinstance(last_execution.output_data, str):
                    output = json.loads(last_execution.output_data)
                else:
                    output = last_execution.output_data
                
                session_id = output.get("session_id")
                if session_id:
                    input_data["session_id"] = session_id
                    log.info(f"✅ Reusing session_id for deep_research: {session_id}")
            except Exception as e:
                log.error(f"Failed to parse previous execution output: {e}")
    # ============================================================

    # Create execution record
    form = WorkflowExecutionForm(
        workflow_id=workflow_id,
        chat_id=body.get("chat_id"),
        message_id=body.get("message_id"),
        input_data=input_data
    )
    execution = WorkflowExecutions.create_execution(user.id, form)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create execution"
        )

    # Fetch credential (service_name is the workflow_type)
    credential = WorkflowCredentials.get_credential_by_service(user.id, service_name)

    # Build config dict & fix endpoint for container
    cfg: Dict[str, Any] = dict(workflow.config or {})
    if "endpoint_url" in cfg:
        cfg["endpoint_url"] = _fix_endpoint_for_container(cfg.get("endpoint_url"))
    # For legacy n8n configs, map flow_id -> workflow_id
    if service_name == "n8n" and "workflow_id" not in cfg and "flow_id" in cfg:
        cfg["workflow_id"] = cfg.get("flow_id")

    # Import executor here to avoid circulars and keep import light
    from open_webui.utils.workflow_executor import execute_workflow as run_workflow

    async def _runner():
        try:
            # mark running
            WorkflowExecutions.update_execution_status(execution.id, status="running")

            api_key = getattr(credential, "api_key", None) if credential else None

            result = await run_workflow(
                workflow_type=service_name,
                config=cfg,
                api_key=api_key,
                input_data=input_data or {},
            )

            if result.get("success"):
                WorkflowExecutions.update_execution_status(
                    execution.id,
                    status="completed",
                    output_data=result.get("output")
                )
            else:
                WorkflowExecutions.update_execution_status(
                    execution.id,
                    status="failed",
                    error_message=result.get("error", "Unknown error")
                )
        except Exception as e:
            log.exception("Workflow execution crashed")
            WorkflowExecutions.update_execution_status(
                execution.id,
                status="failed",
                error_message=str(e)
            )

    # spawn background and return immediately
    asyncio.create_task(_runner())
    return {"id": execution.id, "status": "pending"}


@router.get("/executions/list", response_model=List[WorkflowExecutionModel])
async def get_executions(
    limit: int = 50,
    user: UserModel = Depends(get_verified_user)
):
    """Get execution history for the current user"""
    return WorkflowExecutions.get_executions_by_user_id(user.id, limit)


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionModel)
async def get_execution(
    execution_id: str,
    user: UserModel = Depends(get_verified_user)
):
    """Get a specific execution by ID"""
    execution = WorkflowExecutions.get_execution_by_id(execution_id)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )

    # Check ownership
    if execution.user_id != user.id and getattr(user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    return execution


@router.get("/executions/{execution_id}/status")
async def get_execution_status(
    execution_id: str,
    user: UserModel = Depends(get_verified_user)
):
    """Get the status of a workflow execution"""
    execution = WorkflowExecutions.get_execution_by_id(execution_id)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )

    # Check ownership
    if execution.user_id != user.id and getattr(user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    return {
        "id": execution.id,
        "status": execution.status,
        "started_at": execution.started_at,
        "completed_at": execution.completed_at,
        "error_message": execution.error_message
    }