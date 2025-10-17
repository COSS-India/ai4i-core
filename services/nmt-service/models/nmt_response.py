"""
NMT Response Models
Pydantic models for NMT inference responses
"""

from typing import List
from pydantic import BaseModel


class TranslationOutput(BaseModel):
    """Translation output result"""
    source: str
    target: str
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)


class NMTInferenceResponse(BaseModel):
    """NMT inference response"""
    output: List[TranslationOutput]
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)
