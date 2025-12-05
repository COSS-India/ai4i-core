"""
Transliteration Request Models
Pydantic models for transliteration inference requests
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
    """Text input for transliteration"""
    source: str = Field(..., description="Input text to transliterate")
    
    @validator('source')
    def validate_source_text(cls, v):
        if v is None:
            raise ValueError('Source text cannot be None')
        # Allow empty strings for transliteration (service handles this)
        if len(v) > 10000:
            raise ValueError('Source text cannot exceed 10000 characters')
        return v


class TransliterationInferenceConfig(BaseModel):
    """Transliteration inference configuration"""
    serviceId: str = Field(..., description="Identifier for transliteration service/model")
    language: LanguagePair = Field(..., description="Language pair configuration")
    isSentence: bool = Field(True, description="True for sentence-level, False for word-level transliteration")
    numSuggestions: int = Field(0, description="Number of top-k suggestions (0 for best, >0 for word-level only)")
    
    @validator('serviceId')
    def validate_service_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Service ID cannot be empty')
        return v.strip()
    
    @validator('numSuggestions')
    def validate_num_suggestions(cls, v, values):
        if v < 0 or v > 10:
            raise ValueError('numSuggestions must be between 0 and 10')
        return v


class TransliterationInferenceRequest(BaseModel):
    """Transliteration inference request"""
    input: List[TextInput] = Field(..., description="List of text inputs to transliterate")
    config: TransliterationInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")
    
    @validator('input')
    def validate_input_list(cls, v):
        if not v:
            raise ValueError('At least one text input is required')
        if len(v) > 100:
            raise ValueError('Maximum 100 text inputs allowed per request')
        return v
    
    def dict(self, **kwargs):
        """Override dict to exclude None values"""
        return super().dict(exclude_none=True, **kwargs)

