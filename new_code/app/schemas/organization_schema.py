from pydantic import BaseModel
from typing import Optional

class OrganizationCreate(BaseModel):
    name: str
    description: Optional[str] = None

class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
