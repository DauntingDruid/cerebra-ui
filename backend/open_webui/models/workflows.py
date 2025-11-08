from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Boolean, Text, TIMESTAMP, ForeignKey, Index, or_
from sqlalchemy.sql import func
from open_webui.internal.db import Base, Session
from open_webui.utils.crypto import encrypt_str, decrypt_str

import uuid
from datetime import datetime
import json


####################
# Database Models (SQLAlchemy) - SQLite Compatible
####################

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    workflow_type = Column(String(50), nullable=False)  # 'langflow', 'n8n', 'langchain', 'custom'
    config = Column(Text, nullable=False)  # JSON stored as text
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=False)  # ✅ ADDED: Enable resource sharing
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_workflows_user_id', 'user_id'),
        Index('idx_workflows_is_public', 'is_public'),  # ✅ ADDED: Index for performance
    )


class WorkflowCredential(Base):
    __tablename__ = "workflow_credentials"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    service_name = Column(String(100), nullable=False)
    api_key = Column(Text, nullable=False)  # ENCRYPTED at rest
    endpoint_url = Column(Text, nullable=True)
    additional_config = Column(Text, nullable=True)  # JSON stored as text
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_workflow_creds_user_id', 'user_id'),
    )


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(255), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    chat_id = Column(String(255), nullable=True)
    message_id = Column(String(255), nullable=True)
    input_data = Column(Text, nullable=True)   # JSON stored as text
    output_data = Column(Text, nullable=True)  # JSON stored as text
    status = Column(String(50), default='pending')  # 'pending', 'running', 'completed', 'failed'
    error_message = Column(Text, nullable=True)
    started_at = Column(TIMESTAMP, server_default=func.now())
    completed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index('idx_workflow_executions_workflow_id', 'workflow_id'),
        Index('idx_workflow_executions_chat_id', 'chat_id'),
    )


####################
# Pydantic Schemas (API Models)
####################

class WorkflowModel(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    workflow_type: str
    config: Dict[str, Any]
    is_active: bool = True
    is_public: bool = False  # ✅ ADDED: Resource visibility flag
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowForm(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    workflow_type: str = Field(..., pattern="^(langflow|n8n|langchain|deep_research|custom)$")
    config: Dict[str, Any]
    is_active: bool = True
    is_public: bool = False  # ✅ ADDED: Allow users to make workflows public


class WorkflowCredentialModel(BaseModel):
    id: str
    user_id: str
    service_name: str
    endpoint_url: Optional[str] = None
    additional_config: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowCredentialForm(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=100)
    api_key: Optional[str] = None  # will be encrypted at rest, None for updates if not changing
    endpoint_url: Optional[str] = None
    additional_config: Optional[Dict[str, Any]] = None


class WorkflowExecutionModel(BaseModel):
    id: str
    workflow_id: str
    user_id: str
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    status: str
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkflowExecutionForm(BaseModel):
    workflow_id: str
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None


####################
# Helper functions for JSON conversion
####################

def _dict_to_json(data: Optional[Dict]) -> Optional[str]:
    """Convert dict to JSON string"""
    return json.dumps(data) if data else None


def _json_to_dict(data: Optional[str]) -> Optional[Dict]:
    """Convert JSON string to dict"""
    try:
        return json.loads(data) if data else None
    except Exception:
        return None


def _workflow_to_model_dict(w: Workflow) -> Dict[str, Any]:
    """Build a dict for Pydantic with config parsed to dict."""
    return {
        "id": w.id,
        "user_id": w.user_id,
        "name": w.name,
        "description": w.description,
        "workflow_type": w.workflow_type,
        "config": _json_to_dict(w.config),
        "is_active": w.is_active,
        "is_public": getattr(w, "is_public", False),  # ✅ ADDED: Include is_public in output
        "created_at": w.created_at,
        "updated_at": w.updated_at,
    }


####################
# Database Operations
####################

class Workflows:
    @staticmethod
    def create_workflow(user_id: str, form_data: WorkflowForm) -> Optional[WorkflowModel]:
        try:
            workflow = Workflow(
                id=str(uuid.uuid4()),
                user_id=user_id,
                name=form_data.name,
                description=form_data.description,
                workflow_type=form_data.workflow_type,
                config=_dict_to_json(form_data.config),
                is_active=form_data.is_active,
                is_public=form_data.is_public,  # ✅ ADDED: Set is_public from form
            )
            Session.add(workflow)
            Session.commit()
            Session.refresh(workflow)

            return WorkflowModel.model_validate(_workflow_to_model_dict(workflow))
        except Exception as e:
            print(f"Error creating workflow: {e}")
            Session.rollback()
            return None

    @staticmethod
    def get_workflows_by_user_id(user_id: str) -> List[WorkflowModel]:
        """Get workflows owned by specific user (legacy method - kept for compatibility)"""
        workflows = Session.query(Workflow).filter(Workflow.user_id == user_id).all()
        return [WorkflowModel.model_validate(_workflow_to_model_dict(w)) for w in workflows]

    @staticmethod
    def get_workflows_for_user(user_id: str, user_role: str) -> List[WorkflowModel]:
        """
        ✅ NEW METHOD: Get workflows accessible to user based on role and visibility.
        
        Access rules:
        - Admin: sees all workflows
        - Regular user: sees public workflows + their own private workflows
        
        This enables resource sharing while maintaining privacy.
        """
        if user_role == "admin":
            # Admin sees everything
            workflows = Session.query(Workflow).all()
        else:
            # User sees public workflows OR their own workflows
            workflows = Session.query(Workflow).filter(
                or_(
                    Workflow.is_public == True,
                    Workflow.user_id == user_id
                )
            ).all()
        
        return [WorkflowModel.model_validate(_workflow_to_model_dict(w)) for w in workflows]

    @staticmethod
    def get_workflow_by_id(workflow_id: str) -> Optional[WorkflowModel]:
        try:
            w = Session.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not w:
                return None
            return WorkflowModel.model_validate(_workflow_to_model_dict(w))
        except Exception as e:
            print(f"Error getting workflow: {e}")
            return None

    @staticmethod
    def update_workflow(workflow_id: str, form_data: WorkflowForm) -> Optional[WorkflowModel]:
        try:
            w = Session.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not w:
                return None

            w.name = form_data.name
            w.description = form_data.description
            w.workflow_type = form_data.workflow_type
            w.config = _dict_to_json(form_data.config)
            w.is_active = form_data.is_active
            w.is_public = form_data.is_public  # ✅ ADDED: Update is_public from form
            w.updated_at = datetime.now()

            Session.commit()
            Session.refresh(w)

            return WorkflowModel.model_validate(_workflow_to_model_dict(w))
        except Exception as e:
            print(f"Error updating workflow: {e}")
            Session.rollback()
            return None

    @staticmethod
    def delete_workflow(workflow_id: str) -> bool:
        try:
            w = Session.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not w:
                return False
            Session.delete(w)
            Session.commit()
            return True
        except Exception as e:
            print(f"Error deleting workflow: {e}")
            Session.rollback()
            return False


class WorkflowCredentials:
    @staticmethod
    def create_credential(user_id: str, form_data: WorkflowCredentialForm) -> Optional[WorkflowCredentialModel]:
        try:
            cred = WorkflowCredential(
                id=str(uuid.uuid4()),
                user_id=user_id,
                service_name=form_data.service_name,
                api_key=encrypt_str(form_data.api_key or ""),  # ENCRYPT before storing
                endpoint_url=form_data.endpoint_url,
                additional_config=_dict_to_json(form_data.additional_config),
            )
            Session.add(cred)
            Session.commit()
            Session.refresh(cred)

            model = WorkflowCredentialModel.model_validate(cred)
            model.additional_config = _json_to_dict(cred.additional_config)
            return model
        except Exception as e:
            print(f"Error creating credential: {e}")
            Session.rollback()
            return None

    @staticmethod
    def get_credentials_by_user_id(user_id: str) -> List[WorkflowCredentialModel]:
        creds = Session.query(WorkflowCredential).filter(WorkflowCredential.user_id == user_id).all()
        result: List[WorkflowCredentialModel] = []
        for c in creds:
            m = WorkflowCredentialModel.model_validate(c)
            m.additional_config = _json_to_dict(c.additional_config)
            result.append(m)
        return result

    @staticmethod
    def get_credential_by_service(user_id: str, service_name: str) -> Optional[WorkflowCredential]:
        cred = Session.query(WorkflowCredential).filter(
            WorkflowCredential.user_id == user_id,
            WorkflowCredential.service_name == service_name,
        ).first()
        if cred:
            # DECRYPT before returning so the executor can use it
            try:
                cred.api_key = decrypt_str(cred.api_key or "")
            except Exception:
                pass
        return cred

    @staticmethod
    def update_credential(credential_id: str, user_id: str, form_data: WorkflowCredentialForm) -> Optional[WorkflowCredentialModel]:
        try:
            cred = Session.query(WorkflowCredential).filter(
                WorkflowCredential.id == credential_id,
                WorkflowCredential.user_id == user_id,
            ).first()
            if not cred:
                return None

            # Update fields
            cred.service_name = form_data.service_name
            if form_data.api_key:
                cred.api_key = encrypt_str(form_data.api_key)
            cred.endpoint_url = form_data.endpoint_url
            cred.additional_config = _dict_to_json(form_data.additional_config)
            cred.updated_at = datetime.now()

            Session.commit()
            Session.refresh(cred)

            model = WorkflowCredentialModel.model_validate(cred)
            model.additional_config = _json_to_dict(cred.additional_config)
            return model
        except Exception as e:
            print(f"Error updating credential: {e}")
            Session.rollback()
            return None

    @staticmethod
    def delete_credential(credential_id: str, user_id: str) -> bool:
        try:
            cred = Session.query(WorkflowCredential).filter(
                WorkflowCredential.id == credential_id,
                WorkflowCredential.user_id == user_id,
            ).first()
            if not cred:
                return False
            Session.delete(cred)
            Session.commit()
            return True
        except Exception as e:
            print(f"Error deleting credential: {e}")
            Session.rollback()
            return False


class WorkflowExecutions:
    @staticmethod
    def _exec_to_model_dict(e: WorkflowExecution) -> Dict[str, Any]:
        return {
            "id": e.id,
            "workflow_id": e.workflow_id,
            "user_id": e.user_id,
            "chat_id": e.chat_id,
            "message_id": e.message_id,
            "input_data": _json_to_dict(e.input_data),
            "output_data": _json_to_dict(e.output_data),
            "status": e.status,
            "error_message": e.error_message,
            "started_at": e.started_at,
            "completed_at": e.completed_at,
        }

    @staticmethod
    def create_execution(user_id: str, form_data: WorkflowExecutionForm) -> Optional[WorkflowExecutionModel]:
        try:
            e = WorkflowExecution(
                id=str(uuid.uuid4()),
                workflow_id=form_data.workflow_id,
                user_id=user_id,
                chat_id=form_data.chat_id,
                message_id=form_data.message_id,
                input_data=_dict_to_json(form_data.input_data),
                status='pending',
            )
            Session.add(e)
            Session.commit()
            Session.refresh(e)

            return WorkflowExecutionModel.model_validate(WorkflowExecutions._exec_to_model_dict(e))
        except Exception as e:
            print(f"Error creating execution: {e}")
            Session.rollback()
            return None

    @staticmethod
    def update_execution_status(
        execution_id: str,
        status: str,
        output_data: Optional[Dict] = None,
        error_message: Optional[str] = None
    ) -> Optional[WorkflowExecutionModel]:
        try:
            e = Session.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
            if not e:
                return None

            e.status = status
            if output_data is not None:
                e.output_data = _dict_to_json(output_data)
            if error_message is not None:
                e.error_message = error_message
            if status in ['completed', 'failed']:
                e.completed_at = datetime.now()

            Session.commit()
            Session.refresh(e)

            return WorkflowExecutionModel.model_validate(WorkflowExecutions._exec_to_model_dict(e))
        except Exception as ex:
            print(f"Error updating execution: {ex}")
            Session.rollback()
            return None

    @staticmethod
    def get_executions_by_user_id(user_id: str, limit: int = 50) -> List[WorkflowExecutionModel]:
        rows = (
            Session.query(WorkflowExecution)
            .filter(WorkflowExecution.user_id == user_id)
            .order_by(WorkflowExecution.started_at.desc())
            .limit(limit)
            .all()
        )
        return [WorkflowExecutionModel.model_validate(WorkflowExecutions._exec_to_model_dict(e)) for e in rows]

    @staticmethod
    def get_execution_by_id(execution_id: str) -> Optional[WorkflowExecutionModel]:
        try:
            e = Session.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
            if not e:
                return None
            return WorkflowExecutionModel.model_validate(WorkflowExecutions._exec_to_model_dict(e))
        except Exception as ex:
            print(f"Error getting execution: {ex}")
            return None

    @staticmethod
    def get_last_completed_execution(workflow_id: str, chat_id: str) -> Optional[WorkflowExecutionModel]:
        """
        Get the most recent completed execution for a specific workflow and chat.
        Used for session/thread continuity in deep_research workflows.
        """
        try:
            e = (
                Session.query(WorkflowExecution)
                .filter(
                    WorkflowExecution.workflow_id == workflow_id,
                    WorkflowExecution.chat_id == chat_id,
                    WorkflowExecution.status == "completed"
                )
                .order_by(WorkflowExecution.started_at.desc())
                .first()
            )
            
            if not e:
                return None
                
            return WorkflowExecutionModel.model_validate(WorkflowExecutions._exec_to_model_dict(e))
        except Exception as ex:
            print(f"Error getting last completed execution: {ex}")
            return None