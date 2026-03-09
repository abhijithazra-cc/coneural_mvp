
from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime,JSON
from sqlalchemy import Column, Integer, Text, DateTime
from app.database import Base
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class UserPasswordHistory(Base):
    __tablename__ = "user_password_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    old_password=Column(String, nullable=False)
    modified_password=Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())