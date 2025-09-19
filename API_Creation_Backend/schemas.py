from pydantic import BaseModel, Field, EmailStr
from typing import Optional

# Organizations
class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    admin_email: EmailStr

class OrgOut(BaseModel):
    org_id: int
    name: str
    class Config:
        from_attributes = True

# Suborgs
class SuborgCreate(BaseModel):
    org_id: int
    name: str

class SuborgOut(BaseModel):
    suborg_id: int
    org_id: int
    name: str
    class Config:
        from_attributes = True

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
    suborg_id: int
    name: str
    email: EmailStr

class UserOut(BaseModel):
    user_id: int
    org_id: int
    suborg_id: Optional[int] = None
    name: str
    email: EmailStr
    role: Optional[str] = None
    class Config:
        from_attributes = True

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
