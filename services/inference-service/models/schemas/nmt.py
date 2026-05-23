"""NMT (Neural Machine Translation) service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TextInput(BaseModel):
    """Input for text-based NMT task."""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(..., description="Text to translate")


class LanguagePair(BaseModel):
    """Language pair configuration for NMT."""

    model_config = ConfigDict(populate_by_name=True)

    source_language: str = Field(
        ..., alias="sourceLanguage", description="Source language code (e.g., 'en')"
    )
    target_language: str = Field(
        ..., alias="targetLanguage", description="Target language code (e.g., 'hi')"
    )
    source_script_code: Optional[str] = Field(
        None, alias="sourceScriptCode", description="Source script code (e.g., 'Latn')"
    )
    target_script_code: Optional[str] = Field(
        None, alias="targetScriptCode", description="Target script code (e.g., 'Deva')"
    )


class NMTConfig(BaseModel):
    """Configuration for NMT inference."""

    model_config = ConfigDict(populate_by_name=True)

    service_id: Optional[str] = Field(
        None, alias="serviceId", description="Service ID (optional, resolved by SMR)"
    )
    language: LanguagePair = Field(..., description="Source and target language pair")
    context: Optional[str] = Field(
        None, description="Optional context for context-aware translation"
    )


class NMTInferenceRequest(BaseModel):
    """Request for NMT inference."""

    model_config = ConfigDict(populate_by_name=True)

    input: List[TextInput] = Field(
        ..., min_length=1, max_length=90, description="Text inputs to translate"
    )
    config: NMTConfig = Field(..., description="NMT configuration")


class TranslationOutput(BaseModel):
    """Output from NMT inference."""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(..., description="Original source text")
    target: str = Field(..., description="Translated target text")


class NMTInferenceResponse(BaseModel):
    """Response from NMT inference."""

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    output: List[TranslationOutput] = Field(..., description="Translation results")
    smr_response: Optional[Dict[str, Any]] = Field(
        None, description="Smart Model Router metadata"
    )

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    def dict(self, **kwargs) -> Dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().dict(**kwargs)
