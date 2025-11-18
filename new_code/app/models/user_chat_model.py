from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime
from sqlalchemy import Column, Integer, Text, DateTime
from app.database import Base
from sqlalchemy.sql import func

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    user_query = Column(Text)
    bot_response = Column(Text)
    thread_id=Column(Text)
    user_id=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())