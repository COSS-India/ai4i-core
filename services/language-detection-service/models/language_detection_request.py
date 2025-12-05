"""
Language Detection Request Models
Pydantic models for language detection inference requests
"""

from typing import List, Optional
from pydantic import BaseModel, Field, validator


class TextInput(BaseModel):
    """Text input for language detection"""
    source: str = Field(..., description="Input text to detect language")


class LanguageDetectionInferenceConfig(BaseModel):
    """Configuration for language detection inference"""
    serviceId: str = Field(..., description="Language detection service/model ID")
    
    @validator('serviceId')
    def validate_service_id(cls, v):
        if not v or not v.strip():
            raise ValueError("Service ID cannot be empty")
        return v


class LanguageDetectionInferenceRequest(BaseModel):
    """Request model for language detection inference"""
    input: List[TextInput] = Field(
        ..., 
        description="List of text inputs to detect language", 
        min_items=1
    )
    config: LanguageDetectionInferenceConfig = Field(
        ..., 
        description="Configuration for inference"
    )
    controlConfig: Optional[dict] = Field(
        None, 
        description="Additional control parameters"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "input": [
                    {"source": "नमस्ते दुनिया"},
                    {"source": "Hello world"}
                ],
                "config": {
                    "serviceId": "ai4bharat/indiclid"
                }
            }
        }

