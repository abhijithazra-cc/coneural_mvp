from pydantic import BaseModel
from typing import Optional

class OrganizationCreate(BaseModel):
    name: str
    description: Optional[str] = None

class OrganizationUpdate(BaseModel):
    organization_name: Optional[str] = None
    your_name: Optional[str] = None
    country: Optional[str] = None
    website_url: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    social_handles: Optional[dict] = None
    is_active: Optional[bool] = True
