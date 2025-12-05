"""
Transliteration Response Models
Pydantic models for transliteration inference responses
"""

from typing import List, Union
from pydantic import BaseModel


class TransliterationOutput(BaseModel):
    """Transliteration output result"""
    source: str
    target: Union[str, List[str]]  # Single string or list for top-k suggestions
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)


class TransliterationInferenceResponse(BaseModel):
    """Transliteration inference response"""
    output: List[TransliterationOutput]
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)

