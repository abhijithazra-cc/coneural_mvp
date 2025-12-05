from pydantic import BaseModel
from typing import Optional

class SuborganizationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    organization_id: int

class SuborganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    organization_id: Optional[int] = None
    is_active: Optional[bool] = None
