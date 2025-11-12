from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum

class UserType(str, Enum):
    ADMIN = "ADMIN"
    SUBORG_ADMIN = "SUBORG_ADMIN"
    USER = "USER"

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    user_type: UserType = UserType.ADMIN
    organization_id: Optional[int] = None
    suborganization_id: Optional[int] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    id: int
    username: str
    email: EmailStr
    user_type: UserType
    organization_id: Optional[int] = None
    suborganization_id: Optional[int] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
