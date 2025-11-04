"""
Pydantic models for ASR inference responses.

Adapted from Dhruva-Platform-2 ULCA schemas for ASR service.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class NBestToken(BaseModel):
    """N-best token alternative with confidence scores."""
    word: str = Field(..., description="The word/token")
    tokens: List[Dict[str, float]] = Field(..., description="List of alternative tokens with scores")
    
    class Config:
        json_schema_extra = {
            "example": {
                "word": "hello",
                "tokens": [
                    {"token": "hello", "score": 0.95},
                    {"token": "helo", "score": 0.05}
                ]
            }
        }


class TranscriptOutput(BaseModel):
    """Transcription output for a single audio input."""
    source: str = Field(..., description="The transcribed text")
    nBestTokens: Optional[List[NBestToken]] = Field(None, description="N-best token alternatives (if requested)")
    
    def dict(self, **kwargs):
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class ASRInferenceResponse(BaseModel):
    """Main ASR inference response model."""
    output: List[TranscriptOutput] = Field(..., description="List of transcription results (one per audio input)")
    config: Optional[Dict[str, Any]] = Field(None, description="Response configuration metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "output": [
                    {
                        "source": "Hello, this is a test transcription.",
                        "nBestTokens": None
                    }
                ],
                "config": None
            }
        }
    
    def dict(self, **kwargs):
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)
