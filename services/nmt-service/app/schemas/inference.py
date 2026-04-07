"""
NMT Request / Response Pydantic schemas.
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
        if not v:
            return None
        if len(v) < 2 or len(v) > 10:
            raise ValueError('Script codes must be 2-10 characters')
        return v


class TextInput(BaseModel):
    """Text input for translation"""
    source: str = Field(..., description="Input text to translate")

    @validator('source')
    def validate_source_text(cls, v):
        if v is None:
            return ""
        return v.strip() if isinstance(v, str) else ""


class NMTInferenceConfig(BaseModel):
    """NMT inference configuration"""
    serviceId: Optional[str] = Field(None, description="Identifier for NMT service/model. If not provided, SMR service will be called to select a serviceId.")
    language: LanguagePair = Field(..., description="Language pair configuration")
    context: Optional[str] = Field(None, description="Context string for context-aware translation (required when X-Context-Aware header is set to true)")

    class Config:
        extra = "allow"

    @validator('serviceId')
    def validate_service_id(cls, v):
        if v is not None and v.strip():
            return v.strip()
        return None


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
        """Override dict to exclude None values, but allow context to be passed through"""
        if "exclude_none" in kwargs and kwargs["exclude_none"] is False:
            return super().dict(**kwargs)
        return super().dict(exclude_none=True, **kwargs)


class TranslationOutput(BaseModel):
    """Translation output result"""
    source: str
    target: str

    def dict(self, **kwargs):
        return super().dict(exclude_none=True, **kwargs)


class NMTInferenceResponse(BaseModel):
    """NMT inference response"""
    output: List[TranslationOutput]
    smr_response: Optional[Dict[str, Any]] = None

    def dict(self, **kwargs):
        return super().dict(exclude_none=True, **kwargs)


class TryItRequest(BaseModel):
    """Try-It request wrapper for anonymous access."""
    service_name: str = Field(..., description="Target service name for Try-It (e.g., 'nmt')")
    payload: Dict[str, Any] = Field(..., description="Service request payload (NMTInferenceRequest)")
