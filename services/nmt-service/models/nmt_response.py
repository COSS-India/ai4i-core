"""
NMT Response Models
Pydantic models for NMT inference responses
"""

from typing import List, Optional, Dict, Any
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
    smr_response: Optional[Dict[str, Any]] = None  # SMR response if SMR was used
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)
