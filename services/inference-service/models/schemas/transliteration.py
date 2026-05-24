"""Transliteration service request/response schemas."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field, model_validator


class TextInput(BaseModel):
    """Input for transliteration task."""

    source: str = Field(..., description="Text to transliterate")


class TransliterationLanguagePair(BaseModel):
    """Language pair configuration for transliteration."""

    source_language: str = Field(
        ...,
        alias="sourceLanguage",
        description="Source language code (e.g., 'en', 'hi')",
    )
    target_language: str = Field(
        ...,
        alias="targetLanguage",
        description="Target language code",
    )
    source_script_code: Optional[str] = Field(
        None,
        alias="sourceScriptCode",
        description="Optional source script code",
    )
    target_script_code: Optional[str] = Field(
        None,
        alias="targetScriptCode",
        description="Optional target script code",
    )

    model_config = {"populate_by_name": True}


class TransliterationConfig(BaseModel):
    """Configuration for transliteration inference."""

    service_id: Optional[str] = Field(None, alias="serviceId", description="Service ID")
    language: TransliterationLanguagePair = Field(..., description="Source and target language pair")
    is_sentence: bool = Field(
        True,
        alias="isSentence",
        description="True for sentence-level, False for word-level transliteration",
    )
    num_suggestions: int = Field(
        0,
        alias="numSuggestions",
        ge=0,
        le=10,
        description="Top-k suggestions (0 = best only; >0 word-level only)",
    )
    preserve_case: Optional[bool] = Field(True, description="Preserve case in transliteration")

    model_config = {"populate_by_name": True}

    @computed_field
    @property
    def is_word_level(self) -> bool:
        """Derived from is_sentence — included in model_dump() for Triton mapper."""
        return not self.is_sentence

    @computed_field
    @property
    def top_k(self) -> int:
        """Derived from num_suggestions — included in model_dump() for Triton mapper."""
        return self.num_suggestions


class TransliterationInferenceRequest(BaseModel):
    """Request for transliteration inference."""

    input: List[TextInput] = Field(
        ..., min_length=1, max_length=100, description="Text inputs to transliterate"
    )
    config: TransliterationConfig = Field(..., description="Transliteration configuration")


class TransliterationOutput(BaseModel):
    """Output from transliteration inference."""

    source: str = Field(..., description="Original source text")
    target: str = Field(..., description="Transliterated target text")


class TransliterationInferenceResponse(BaseModel):
    """Response from transliteration inference."""

    output: List[TransliterationOutput] = Field(..., description="Transliteration results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
