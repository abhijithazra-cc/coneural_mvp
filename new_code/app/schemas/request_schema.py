from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum


class AskRequest(BaseModel):
    org_id: int
    user_id: int
    q: str
    top_k:int
    stream: Optional[bool] = True
