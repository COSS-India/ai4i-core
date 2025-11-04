"""
NMT Request Models
Pydantic models for NMT inference requests
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, validator


class LanguagePair(BaseModel):
    """Language pair configuration"""
    sourceLanguage: str = Field(..., description="Source language code (e.g., 'en', 'hi', 'ta')")
    targetLanguage: str = Field(..., description="Target language code")
    sourceScriptCode: Optional[str] = Field(None, description="Script code for source (e.g., 'Deva', 'Arab')")
    targetScriptCode: Optional[str] = Field(None, description="Script code for target")
    
    @validator('sourceLanguage', 'targetLanguage')
    def validate_language_codes(cls, v):
        if not v or len(v) < 2 or len(v) > 3:
            raise ValueError('Language codes must be 2-3 characters')
        return v
    
    @validator('sourceScriptCode', 'targetScriptCode')
    def validate_script_codes(cls, v):
        if v is not None and (len(v) < 2 or len(v) > 10):
            raise ValueError('Script codes must be 2-10 characters')
        return v


class TextInput(BaseModel):
    """Text input for translation"""
    source: str = Field(..., description="Input text to translate")
    
    @validator('source')
    def validate_source_text(cls, v):
        if not v or not v.strip():
            raise ValueError('Source text cannot be empty')
        if len(v) > 10000:
            raise ValueError('Source text cannot exceed 10000 characters')
        return v.strip()


class NMTInferenceConfig(BaseModel):
    """NMT inference configuration"""
    serviceId: str = Field(..., description="Identifier for NMT service/model")
    language: LanguagePair = Field(..., description="Language pair configuration")
    
    @validator('serviceId')
    def validate_service_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Service ID cannot be empty')
        return v.strip()


class NMTInferenceRequest(BaseModel):
    """NMT inference request"""
    input: List[TextInput] = Field(..., description="List of text inputs to translate")
    config: NMTInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")
    
    @validator('input')
    def validate_input_list(cls, v):
        if not v:
            raise ValueError('At least one text input is required')
        if len(v) > 90:
            raise ValueError('Maximum 90 text inputs allowed per request')
        return v
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)
