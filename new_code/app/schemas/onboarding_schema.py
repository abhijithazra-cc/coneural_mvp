from pydantic import BaseModel, EmailStr, AnyUrl
from typing import List, Optional, Dict, Any
from enum import Enum

class SignupRequest(BaseModel):
    organization_name: str
    admin_name: str
    admin_email: EmailStr
    password: str
    description: Optional[str] = None  # optional tagline/desc

class SignupResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization: Dict[str, Any]  # {id,name,description}
    admin_user: Dict[str, Any]    # {id,name,email,user_type}

class OrgProfileUpdate(BaseModel):
    website_url: Optional[AnyUrl] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    social_handles: Optional[Dict[str, str]] = None  # {"twitter":"...", "linkedin":"..."}

class DepartmentBulkCreate(BaseModel):
    organization_id: int
    departments: List[str]  # names e.g. ["HR","Finance & Accounts","IT & Technical Support"]

class RoleEnum(str, Enum):
    ADMIN = "ADMIN"
    DEPT_AUTHOR = "DEPT_AUTHOR"  # maps to USER + is_author=True
    USER = "USER"

class InviteUserItem(BaseModel):
    email: EmailStr
    role: RoleEnum
    department_names: List[str]  # by names (frontend picks chips)
    neural_cap: Optional[int] = 1000000

class InviteUsersRequest(BaseModel):
    organization_id: int
    invites: List[InviteUserItem]

class InviteUsersResponse(BaseModel):
    created_users: List[Dict[str, Any]]  # [{id,email,role,departments}]
