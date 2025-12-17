
from sqlalchemy import (
    Column, Integer, Boolean,Computed, ForeignKey, UniqueConstraint, DateTime, func, BigInteger
)
from app.database import Base
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class UserLicenses(Base):
    __tablename__ = "user_licenses"   
    id = Column(Integer, primary_key=True, index=True)

    dept_id = Column(Integer, ForeignKey("department.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    allocated_licenses = Column(Integer, nullable=False, default=0)
    total_licenses = Column(Integer, nullable=False, server_default="0")

    used_licenses = Column(Integer, nullable=False, server_default="0")

# auto calculated: total - used
    balance_licenses = Column(
    Integer, Computed("allocated_licenses - used_licenses", persisted=True)
)

# auto calculated: licenses * 100000
    allocated_token = Column(Integer, Computed("allocated_licenses * 100000", persisted=True))

    used_token = Column(Integer, nullable=False, server_default="0")

# auto calculated: total_token - used_token
    balance_token = Column(Integer, Computed("allocated_token - used_token", persisted=True))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())