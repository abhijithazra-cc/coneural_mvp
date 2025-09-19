from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, BigInteger, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

Base = declarative_base()

# EXISTING
class Organization(Base):
    __tablename__ = "organizations"
    org_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:   Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class User(Base):
    __tablename__ = "users"
    user_id:   Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id:    Mapped[int] = mapped_column(Integer, nullable=False)
    suborg_id: Mapped[int | None] = mapped_column(Integer)
    name:      Mapped[str] = mapped_column(String(255), nullable=False)  # added via ALTER TABLE
    email:     Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role:      Mapped[str | None] = mapped_column(String(50), default="user")
    created_at:Mapped[datetime | None] = mapped_column(DateTime)

# NEW
class SubOrganization(Base):
    __tablename__ = "sub_organizations"
    suborg_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id:    Mapped[int] = mapped_column(ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False)
    name:      Mapped[str] = mapped_column(String(255), nullable=False)
    created_at:Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_suborg_org_name"),)

class Domain(Base):
    __tablename__ = "domains"
    domain_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id:    Mapped[int] = mapped_column(ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False)
    suborg_id: Mapped[int] = mapped_column(ForeignKey("sub_organizations.suborg_id", ondelete="CASCADE"), nullable=False)
    name:      Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("suborg_id", "name", name="uq_domain_suborg_name"),)

class OrgDocument(Base):
    __tablename__ = "org_documents"
    doc_id:    Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id:    Mapped[int] = mapped_column(ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False)
    suborg_id: Mapped[int] = mapped_column(ForeignKey("sub_organizations.suborg_id", ondelete="CASCADE"), nullable=False)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.domain_id", ondelete="CASCADE"), nullable=False)
    user_id:   Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))

    filename:   Mapped[str] = mapped_column(String(512), nullable=False)
    mimetype:   Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_bytes: Mapped[bytes] = mapped_column(LONGBLOB, nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text)
    uploaded_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
