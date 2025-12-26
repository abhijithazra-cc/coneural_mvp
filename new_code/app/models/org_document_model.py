from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from app.models.base import Base

class OrgDocument(Base):
    __tablename__ = "org_documents"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    dept_id = Column(Integer, ForeignKey("Departments.id", ondelete="CASCADE"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    filename = Column(String(512), nullable=False)
    mime_type = Column(String(128))
    size_bytes = Column(Integer)

    created_at = Column(DateTime, server_default=func.now())
