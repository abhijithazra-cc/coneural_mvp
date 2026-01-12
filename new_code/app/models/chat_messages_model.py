from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime,JSON
from sqlalchemy import Column, Integer, Text, DateTime
from app.database import Base
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base



class DeviceType(str,PyEnum):
    WEB="WEB"
    ANDROID="ANDROID"
    IOS="IOS"
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(Text)
    response = Column(Text)
    thread_id=Column(Integer, ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False)
    user_id=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    unanswer_query=Column(Boolean,default=False)
    tokens=Column(Integer,default=0)
    citation=Column(JSON,nullable=True)
    device_type=Column(SAEnum(DeviceType), nullable=False, default=DeviceType.WEB)
    html_response=Column(JSON,nullable=True)
    created_at = Column(DateTime, server_default=func.now())