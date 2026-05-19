from sqlalchemy import Column, String, Float, DateTime, Text
from sqlalchemy.sql import func
from database import Base
from sqlalchemy import Column, String, Float, DateTime, Text, Integer
class User(Base):
    __tablename__ = "users"
    id            = Column(String, primary_key=True)
    username      = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at    = Column(DateTime, server_default=func.now())

class AgentState(Base):
    __tablename__ = "agent_states"
    user_id    = Column(String, primary_key=True)
    A_matrix   = Column(Text, nullable=False)   # JSON string of 12x12 matrix
    b_vector   = Column(Text, nullable=False)   # JSON string of 12-dim vector
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class ListenHistory(Base):
    __tablename__ = "listen_history"
    id         = Column(Integer, primary_key=True, autoincrement=True)  # ← was String
    user_id    = Column(String, nullable=False)
    track_id   = Column(String, nullable=False)
    track_name = Column(String, nullable=False)
    reward     = Column(Float,  nullable=False)
    played_at  = Column(DateTime, server_default=func.now())