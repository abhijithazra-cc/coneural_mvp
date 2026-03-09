
from sqlalchemy import (
    Column, Integer, Boolean,Computed, ForeignKey, UniqueConstraint, DateTime, func, BigInteger
)
from app.database import Base
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func


class DepartmentLicenses(Base):
    __tablename__ = "department_licenses"   
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    dept_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    allocated_licenses = Column(Integer, nullable=False, default=0)
    total_licenses = Column(Integer, nullable=False, server_default="0")

    used_licenses = Column(Integer, nullable=False, server_default="0")

# auto calculated: total - used
    balance_licenses = Column(
    Integer, Computed("allocated_licenses - used_licenses", persisted=True)
)

# auto calculated: licenses * 100000
    allocated_tokens = Column(Integer, Computed("allocated_licenses * 100000", persisted=True))

    used_tokens = Column(Integer, nullable=False, server_default="0")

# auto calculated: total_token - used_token
    balance_tokens = Column(Integer, Computed("allocated_tokens - used_tokens", persisted=True))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())