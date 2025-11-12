from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.sql import func
from app.database import Base

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(String(1024))
    is_active = Column(Boolean, default=True)

    # Optional org profile fields (you already created these)
    website_url = Column(String(512))
    industry = Column(String(128))
    company_size = Column(String(64))
    social_handles = Column(JSON)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
