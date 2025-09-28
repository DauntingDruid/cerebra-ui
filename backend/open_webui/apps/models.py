from sqlalchemy import Column, Integer, String, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from open_webui.internal.db import Base  # Assuming Base is defined in config.py or env.py

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    framework = Column(String)  # e.g., "n8n", "langflow"
    config = Column(JSON)  # Store JSON config or flow ID
    user_id = Column(Integer, ForeignKey("users.id"))  # Assuming a users table exists
    user = relationship("User", back_populates="workflows")
    created_at = Column(DateTime, default=func.now())

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    service = Column(String, index=True)  # e.g., "n8n", "langflow", "serpapi"
    key_value = Column(String)  # Store encrypted value (add encryption logic if needed)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="api_keys")
    created_at = Column(DateTime, default=func.now())

# Assuming User model exists elsewhere; add back_populates if needed
# from open_webui.models.user import User  # If separate
# User.workflows = relationship("Workflow", back_populates="user")
# User.api_keys = relationship("ApiKey", back_populates="user")