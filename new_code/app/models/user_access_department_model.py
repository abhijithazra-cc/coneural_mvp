from sqlalchemy import (
    Column, Integer, Boolean, ForeignKey, UniqueConstraint, DateTime, func, BigInteger
)
from app.database import Base
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class UserType(str, PyEnum):
    ADMIN = "ADMIN"
    AUTHOR = "AUTHOR"
    USER = "USER"
    DEPT_ADMIN = "DEPT_ADMIN"

class UserAccessDepartment(Base):
    __tablename__ = "user_access_department"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    dept_id = Column(Integer, ForeignKey("department.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    user_type = Column(SAEnum(UserType), nullable=False, default=UserType.USER)

    created_at = Column(DateTime, server_default=func.now())

