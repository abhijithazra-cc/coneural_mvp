from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
class UserThread(BaseModel):

      user_id:int
      organization_id: Optional[int] = None
      