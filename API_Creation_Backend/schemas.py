
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from langchain_core.documents import Document


# Organizations

class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    admin_email: EmailStr


class OrgAdminOut(BaseModel):
    user_id: int
    name: str
    email: EmailStr
    role: str

    class Config:
        from_attributes = True


class OrgOut(BaseModel):
    org_id: int
    name: str
    isDeleted: Optional[bool] = None
    admin: Optional[OrgAdminOut] = None  # include org admin details

    class Config:
        from_attributes = True


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    isDeleted: Optional[bool] = None



# Suborgs

class SuborgCreate(BaseModel):
    org_id: int
    name: str
    admin_email: EmailStr
    admin_name: Optional[str] = None


class SuborgAdminOut(BaseModel):
    user_id: int
    name: str
    email: EmailStr
    role: str

    class Config:
        from_attributes = True


class SuborgOut(BaseModel):
    suborg_id: int
    org_id: int
    name: str
    isDeleted: Optional[bool] = None
    admin: Optional[SuborgAdminOut] = None  # include suborg admin details

    class Config:
        from_attributes = True


class SuborgUpdate(BaseModel):
    name: Optional[str] = None
    isDeleted: Optional[bool] = None



# Domains

class DomainCreate(BaseModel):
    org_id: int
    suborg_id: int
    name: str
    description: Optional[str] = None


class DomainOut(BaseModel):
    domain_id: int
    org_id: int
    suborg_id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class DomainUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# Users

class UserCreate(BaseModel):
    org_id: int
    suborg_id: Optional[int] = None
    name: str
    email: EmailStr


class UserOut(BaseModel):
    user_id: int
    org_id: int
    suborg_id: Optional[int] = None
    name: str
    email: EmailStr
    role: Optional[str] = None
    isDeleted: Optional[bool] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None  
    isDeleted: Optional[bool] = None


# Documents

class OrgDocumentOut(BaseModel):
    doc_id: int
    org_id: int
    suborg_id: int
    domain_id: int
    filename: str
    mimetype: Optional[str] = None
    size_bytes: Optional[int] = None

    class Config:
        from_attributes = True



# Access control

class AccessGrant(BaseModel):
    user_id: int
    domain_id: int


class AccessRevoke(BaseModel):
    user_id: int
    domain_id: int


class AccessOut(BaseModel):
    user_id: int
    domain_id: int

    class Config:
        from_attributes = True


# For admin management endpoints (promote/demote)
class AdminTarget(BaseModel):
    user_id: int



# Q&A

class AskRequest(BaseModel):
    org_id: int
    suborg_id: int
    query: str  


class AskResponse(BaseModel):
    allowed_domains_used: List[int]
    sources: List[Document]   # doc_ids used
    answer: str

