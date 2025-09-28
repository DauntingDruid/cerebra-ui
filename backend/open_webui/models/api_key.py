from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from backend.models.base import Base
from backend.models.user import User
from backend.core.security import encrypt_value

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    service = Column(String, index=True)  # e.g., "n8n", "langflow", "serpapi"
    key_value = Column(String)  # Encrypted
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.key_value:
            self.key_value = encrypt_value(self.key_value)