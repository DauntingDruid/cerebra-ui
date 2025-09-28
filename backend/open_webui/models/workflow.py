from sqlalchemy import Column, String, JSON, Integer, ForeignKey
from sqlalchemy.orm import relationship
from backend.models.base import Base
from backend.models.user import User

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    framework = Column(String)  # e.g., "n8n", "langflow"
    config = Column(JSON)  # Store JSON or flow ID
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User")