from datetime import datetime
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional



class UserRegisterRequest(BaseModel):
    tenant_id: str = Field(..., example="acme-corp-5d448a")
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: Optional[str] = Field(None, min_length=8, description="If not provided, a random password will be generated")
    services: List[str] = Field(..., example=["tts", "asr"])
    is_approved: bool = Field(False, description="Indicates if the user is approved by tenant admin")



class UserRegisterResponse(BaseModel):
    user_id: int
    tenant_id: str
    username: str
    email: str
    services: List[str]
    created_at: datetime
