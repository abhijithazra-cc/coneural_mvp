from sqlalchemy import JSON, Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime,VARCHAR
from sqlalchemy import Column, Integer, Text, DateTime
from app.database import Base
from sqlalchemy.sql import func

class ChatThreads(Base):
    __tablename__ = "chat_threads"


    id=Column(Integer,primary_key=True, index=True)
    user_id=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    llm_provider = Column(VARCHAR(255), nullable=True)
    description = Column(Text, nullable=True)
    document_ids = Column(JSON, nullable=True)  # Store document IDs as a comma-separated string
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())