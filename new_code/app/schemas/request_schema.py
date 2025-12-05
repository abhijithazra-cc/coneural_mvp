from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum

from enum import Enum
class OptionEnum(str, Enum):
    opt1 = 1
    opt2 = 2
    opt3 = 3
class AskRequest(BaseModel):
    selected:OptionEnum
    org_id: int
    user_id: int
    q: str
    top_k:int
    stream: Optional[bool] = True
class AskRequestOnDocument(BaseModel):
    selected:OptionEnum
    doc_id:list[int]
    org_id: int
    user_id: int
    q: str
    top_k:int
    stream: Optional[bool] = True
