from sqlalchemy import Column, Integer, JSON, ForeignKey
from ...internal.db import Base  # Adjust import based on your db setup

class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    graph = Column(JSON, nullable=False)  # Serialized graph as JSON