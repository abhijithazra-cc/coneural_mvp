from pydantic import BaseModel
from typing import Optional

class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    org_id: int


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    org_id: Optional[int] = None
    is_active: Optional[bool] = None
