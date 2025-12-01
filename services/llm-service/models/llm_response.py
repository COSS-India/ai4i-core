"""
LLM Response Models
Pydantic models for LLM inference responses
"""

from typing import List
from pydantic import BaseModel


class LLMOutput(BaseModel):
    """LLM output result"""
    source: str
    target: str
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)


class LLMInferenceResponse(BaseModel):
    """LLM inference response"""
    output: List[LLMOutput]
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)

