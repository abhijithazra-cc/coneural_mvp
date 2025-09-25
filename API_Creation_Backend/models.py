from datetime import datetime
from sqlalchemy import (
    Integer, String, Text, DateTime, ForeignKey, BigInteger,
    UniqueConstraint, JSON
)
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

Base = declarative_base()



class Organization(Base):
    __tablename__ = "organizations"

    org_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    isDeleted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # soft delete flag


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False
    )
    suborg_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sub_organizations.suborg_id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str | None] = mapped_column(String(50), default="user")  # "user", "suborg_admin", "org_admin"
    isDeleted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # soft delete flag
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ----------------- New Tables -----------------
class SubOrganization(Base):
    __tablename__ = "sub_organizations"

    suborg_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    isDeleted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # soft delete flag

    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_suborg_org_name"),)


class Domain(Base):
    __tablename__ = "domains"

    domain_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False
    )
    suborg_id: Mapped[int] = mapped_column(
        ForeignKey("sub_organizations.suborg_id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # HR/Finance/IT/...
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("suborg_id", "name", name="uq_domain_suborg_name"),)


class OrgDocument(Base):
    __tablename__ = "org_documents"

    doc_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False
    )
    suborg_id: Mapped[int] = mapped_column(
        ForeignKey("sub_organizations.suborg_id", ondelete="CASCADE"), nullable=False
    )
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.domain_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mimetype: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_bytes: Mapped[bytes] = mapped_column(
        LONGBLOB, nullable=False
    )  # raw file bytes (later you can replace with S3/GCS path)
    content_text: Mapped[str | None] = mapped_column(Text)  # extracted text for indexing
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class UserDomainAccess(Base):
    __tablename__ = "user_domain_access"

    uda_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.domain_id", ondelete="CASCADE"), nullable=False
    )
    granted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "domain_id", name="uq_user_domain"),)


# ----------------- For Semantic Search -----------------
class DocEmbedding(Base):
    __tablename__ = "doc_embeddings"

    embed_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        ForeignKey("org_documents.doc_id", ondelete="CASCADE"), nullable=False
    )
    chunk_text: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON)  # ✅ JSON array of floats
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
