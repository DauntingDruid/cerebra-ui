"""
Image Session Tracking Model
Stores metadata for each image generation in a conversational chain
"""
from open_webui.internal.db import Base, get_db
from sqlalchemy import BigInteger, Column, String, Text, JSON, ForeignKey, Index
from pydantic import BaseModel, ConfigDict
from typing import Optional, Literal  
from uuid import uuid4
import time
import logging

log = logging.getLogger(__name__)

####################
# ORM Model
####################

class ImageSession(Base):
    __tablename__ = "image_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    chat_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    file_id = Column(String, ForeignKey("file.id"), nullable=False)
    parent_session_id = Column(String, ForeignKey("image_sessions.id"), nullable=True)
    
    prompt = Column(Text, nullable=False)
    optimized_prompt = Column(Text, nullable=True)
    mode = Column(String, nullable=False)  
    
    fal_seed = Column(BigInteger, nullable=True)
    meta_json = Column(JSON, nullable=True)
    
    created_at = Column(BigInteger)  
    updated_at = Column(BigInteger)
    
  
    __table_args__ = (
        Index("ix_image_sessions_chat_user_created", "chat_id", "user_id", "created_at"),
    )

####################
# Pydantic Models (v2)
####################

class ImageSessionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    chat_id: str
    user_id: str
    file_id: str
    parent_session_id: Optional[str] = None
    
    prompt: str
    optimized_prompt: Optional[str] = None
    mode: Literal["text2img", "img2img"]  
    
    fal_seed: Optional[int] = None
    meta_json: Optional[dict] = None
    
    created_at: int
    updated_at: int

class ImageSessionForm(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    chat_id: str
    user_id: str
    file_id: str
    parent_session_id: Optional[str] = None
    prompt: str
    optimized_prompt: Optional[str] = None
    mode: Literal["text2img", "img2img"]  
    fal_seed: Optional[int] = None
    meta_json: Optional[dict] = None

####################
# Repository Class
####################

class ImageSessionsTable:
    def create_session(self, form_data: ImageSessionForm) -> ImageSessionModel:
        """Create a new image generation session"""
        with get_db() as db:
            try:
                timestamp = int(time.time())
                session = ImageSession(
                    **form_data.model_dump(),
                    created_at=timestamp,
                    updated_at=timestamp
                )
                db.add(session)
                db.commit()
                db.refresh(session)
                
                result = ImageSessionModel.model_validate(session)
                log.info(f"Created session {result.id} for chat {result.chat_id}")
                return result
            except Exception as e:
                db.rollback()
                log.error(f"Failed to create session: {e}", exc_info=True) 
                raise
    
    def get_session_by_id(self, session_id: str) -> Optional[ImageSessionModel]:
        """Get a session by ID"""
        with get_db() as db:
            try:
                session = db.query(ImageSession).filter_by(id=session_id).first()
                return ImageSessionModel.model_validate(session) if session else None
            except Exception as e:
                log.error(f"Failed to get session {session_id}: {e}", exc_info=True)  
                return None
    
    def get_last_session(self, chat_id: str, user_id: str) -> Optional[ImageSessionModel]:
        """Get the most recent session for a chat"""
        with get_db() as db:
            try:
                session = (
                    db.query(ImageSession)
                    .filter_by(chat_id=chat_id, user_id=user_id)
                    .order_by(ImageSession.created_at.desc())
                    .first()
                )
                return ImageSessionModel.model_validate(session) if session else None
            except Exception as e:
                log.error(f"Failed to get last session for chat {chat_id}: {e}", exc_info=True)  
                return None
    
    def get_session_chain(self, session_id: str, max_depth: int = 50) -> list[ImageSessionModel]:
        """
        Get the full chain of parent sessions
        Returns: [current_session, parent, grandparent, ...]
        """
        chain = []
        current_id = session_id
        depth = 0
        
        with get_db() as db:
            try:
                while current_id and depth < max_depth:
                    session = db.query(ImageSession).filter_by(id=current_id).first()
                    if not session:
                        break
                    
                    chain.append(ImageSessionModel.model_validate(session))
                    current_id = session.parent_session_id
                    depth += 1
                
                if depth >= max_depth:
                    log.warning(f"Session chain truncated at depth {max_depth}")
                
                return chain
            except Exception as e:
                log.error(f"Failed to get session chain: {e}", exc_info=True)  
                return chain

# Singleton instance
ImageSessions = ImageSessionsTable()