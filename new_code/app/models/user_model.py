from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime,Text
from sqlalchemy.sql import func
from app.database import Base



class RegisterBy(str,PyEnum):
    GOOGLE = "GOOGLE"
    MICROSOFT = "MICROSOFT"
    EMAIL = "EMAIL"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True,  nullable=False)
    username = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    registered_by=Column(SAEnum(RegisterBy), nullable=False, default=RegisterBy.EMAIL)
    register_id=Column(String(255), nullable=True)  # e.g., Google or Microsoft ID
    access_token=Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
