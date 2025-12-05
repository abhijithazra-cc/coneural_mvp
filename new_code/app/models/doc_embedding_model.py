from sqlalchemy import Column, Integer, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.mysql import JSON
from app.models.base import Base

class DocEmbedding(Base):
    __tablename__ = "doc_embeddings"
    id = Column(Integer, primary_key=True, index=True)
    org_document_id = Column(Integer, ForeignKey("org_documents.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    suborg_id = Column(Integer, ForeignKey("suborganizations.id", ondelete="CASCADE"), nullable=False)

    chunk_id = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
