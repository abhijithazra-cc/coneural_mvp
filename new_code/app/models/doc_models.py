from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Index,LargeBinary
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

# class OrgDocument(Base):
#     __tablename__ = "org_documents"

#     id = Column(Integer, primary_key=True, index=True)
#     org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
#     suborganization_id = Column(Integer, ForeignKey("suborganizations.id", ondelete="SET NULL"), nullable=True, index=True)
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
#         Index("idx_docs_org_sub", "org_id", "suborganization_id"),
#     )

class OrgDocument(Base):
    __tablename__ = "org_documents"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    suborg_id = Column(Integer, ForeignKey("suborganizations.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    title = Column(String(512), nullable=False)
    filename = Column(String(512), nullable=False)
    mime_type = Column(String(128))
    size_bytes = Column(Integer)
    file_bytes=Column(LONGBLOB)
    hash_bytes=Column(LargeBinary)
    chunks = relationship("DocChunk", back_populates="document", cascade="all, delete-orphan")
    created_at = Column(DateTime, server_default=func.now())

class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("org_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    # denormalized for fast filtering (optional but handy)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    suborg_id = Column(Integer, ForeignKey("suborganizations.id", ondelete="SET NULL"), nullable=True, index=True)

    chunk_index = Column(Integer, nullable=False)  # 0..N
    content = Column(Text, nullable=False)         # chunk text
    embedding = Column(JSON, nullable=True)        # store vector as JSON array (float list)

    created_at = Column(DateTime, server_default=func.now())

    # Relations
    document = relationship("OrgDocument", back_populates="chunks")

    __table_args__ = (
        Index("idx_chunks_org_sub", "org_id", "suborg_id"),
    )
