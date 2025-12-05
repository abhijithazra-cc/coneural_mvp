from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class UserType(str, PyEnum):
    ADMIN = "ADMIN"
    AUTHOR = "AUTHOR"
    USER = "USER"
    DEPT_HEAD="DEPT_HEAD"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    user_type = Column(SAEnum(UserType), nullable=False, default=UserType.USER)

    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    suborganization_id = Column(Integer, ForeignKey("suborganizations.id", ondelete="SET NULL"), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
