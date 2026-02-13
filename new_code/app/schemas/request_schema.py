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

    # org_id: int

    q: str
    top_k:int




class AskRequestOnDocument(BaseModel):
 
    document_id:list[int]
    # org_id: int
    q: str
    top_k:int

