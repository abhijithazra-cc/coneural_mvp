from sqlalchemy import (
    Column, Integer, Boolean, ForeignKey, UniqueConstraint, DateTime, func, BigInteger
)
from app.database import Base

class UserDomainAccess(Base):
    __tablename__ = "user_domain_access"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    suborg_id = Column(Integer, ForeignKey("suborganizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    can_read = Column(Boolean, default=True)
    can_upload = Column(Boolean, default=False)
    is_author = Column(Boolean, default=False)
    neural_cap = Column(BigInteger, default=1_000_000)  # 1m “neurals” by default

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("org_id", "suborg_id", "user_id", name="uq_access_org_sub_user"),
    )
