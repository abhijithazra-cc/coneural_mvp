from sqlalchemy import Computed, Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.sql import func
from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    description = Column(String(1024))

    # Optional org profile fields (you already created these)
    website_url = Column(String(512))
    industry = Column(String(128))
    country = Column(String(128))
    company_size = Column(String(64))
    social_handles = Column(JSON)
    is_active = Column(Boolean, default=True)
    total_licenses = Column(Integer, nullable=False, server_default="0")

    used_licenses = Column(Integer, nullable=False, server_default="0")

# auto calculated: total - used
    balance_licenses = Column(
    Integer, Computed("total_licenses - used_licenses", persisted=True)
)

# auto calculated: licenses * 100000
    total_tokens = Column(Integer, Computed("total_licenses * 100000", persisted=True))

    used_tokens = Column(Integer, nullable=False, server_default="0")

# auto calculated: total_tokens - used_tokens
    balance_tokens = Column(Integer, Computed("total_tokens - used_tokens", persisted=True))

    created_at = Column(DateTime, server_default=func.now())

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
