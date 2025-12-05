# from pydantic import BaseModel

# class AccessGrant(BaseModel):
#     org_id: int
#     suborg_id: int
#     user_id: int
#     can_read: bool = True
#     can_upload: bool = False
#     is_author: bool = False

# class AccessRevoke(BaseModel):
#     org_id: int
#     suborg_id: int
#     user_id: int



# app/schemas/access_schema.py
from pydantic import BaseModel, Field
from typing import Optional

class AccessGrant(BaseModel):
    org_id: int = Field(..., description="Organization that owns the domain")
    domain_id: int = Field(..., description="Department / domain id")
    user_id: int = Field(..., description="User to grant access to")
    can_read: bool = Field(True, description="Allow user to query/ask questions in this domain")
    can_upload: bool = Field(False, description="Allow user to upload docs into this domain")
    is_author: bool = Field(False, description="Author implies upload & read")
    neural_cap: Optional[int] = Field(None, description="Optional usage cap for this user+domain")

class AccessRevoke(BaseModel):
    org_id: int
    domain_id: int
    user_id: int

