from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


class VoiceGender(str, Enum):
    """Voice gender enumeration."""
    MALE = "male"
    FEMALE = "female"


class VoiceAge(str, Enum):
    """Voice age category enumeration."""
    YOUNG = "young"
    ADULT = "adult"
    SENIOR = "senior"


class VoiceMetadata(BaseModel):
    """Voice metadata model."""
    voice_id: str
    name: str
    gender: VoiceGender
    age: VoiceAge = VoiceAge.ADULT
    languages: List[str]
    model_id: str
    sample_rate: int = 22050
    description: Optional[str] = None
    is_active: bool = True


class VoiceListRequest(BaseModel):
    """Voice list request with filtering options."""
    language: Optional[str] = None
    gender: Optional[VoiceGender] = None
    age: Optional[VoiceAge] = None
    is_active: Optional[bool] = True


class VoiceListResponse(BaseModel):
    """Voice list response with metadata."""
    voices: List[VoiceMetadata]
    total: int
    filtered: int
