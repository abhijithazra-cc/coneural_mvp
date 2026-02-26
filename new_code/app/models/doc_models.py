from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Index,LargeBinary,Enum as SAEnum
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from enum import Enum as PyEnum
# class OrgDocument(Base):
#     __tablename__ = "org_documents"

#     id = Column(Integer, primary_key=True, index=True)
#     org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
#     Department_id = Column(Integer, ForeignKey("Departments.id", ondelete="SET NULL"), nullable=True, index=True)
#     uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

#     title = Column(String(512), nullable=False)
#     filename = Column(String(512), nullable=False)
#     mime_type = Column(String(128))
#     size_bytes = Column(Integer)

#     is_active = Column(Boolean, default=True)
#     created_at = Column(DateTime, server_default=func.now())

#     # Relations
#     chunks = relationship("DocChunk", back_populates="document", cascade="all, delete-orphan")

#     __table_args__ = (
#         Index("idx_docs_org_sub", "org_id", "Department_id"),
#     )


class ScopeType(str, PyEnum):
    department = "department"
    global_scope = "global"
   

class OrgDocument(Base):
    __tablename__ = "org_documents"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    dept_id=Column(Integer,ForeignKey("departments.id",ondelete="CASCADE"),nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    scope=Column(SAEnum(ScopeType),nullable=False,default=ScopeType.department)
    tag=Column(String(256),nullable=True)
    title = Column(String(512), nullable=False)
    filename = Column(String(512), nullable=False)
    mime_type = Column(String(128))
    size_bytes = Column(Integer)
    file_path=Column(String(1024))
    file_bytes=Column(LONGBLOB)
    hash_bytes=Column(LargeBinary)
    created_at = Column(DateTime, server_default=func.now())

class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("org_documents.id", ondelete="CASCADE"), nullable=False, index=True)

    content = Column(Text, nullable=False)         # chunk text


    created_at = Column(DateTime, server_default=func.now())

