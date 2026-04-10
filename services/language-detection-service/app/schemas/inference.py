"""
Language Detection Request & Response Models

Pydantic models for language detection inference requests and responses.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


# ── Request models ──────────────────────────────────────────────────


class TextInput(BaseModel):
    """Text input for language detection."""

    source: str = Field(..., description="Input text to detect language")


class LanguageDetectionInferenceConfig(BaseModel):
    """Configuration for language detection inference."""

    serviceId: str = Field(..., description="Language detection service/model ID")

    @validator("serviceId")
    def validate_service_id(cls, v):
        if not v or not v.strip():
            raise ValueError("Service ID cannot be empty")
        return v


class LanguageDetectionInferenceRequest(BaseModel):
    """Request model for language detection inference."""

    input: List[TextInput] = Field(
        ...,
        description="List of text inputs to detect language",
        min_items=1,
    )
    config: LanguageDetectionInferenceConfig = Field(
        ...,
        description="Configuration for inference",
    )
    controlConfig: Optional[dict] = Field(
        None,
        description="Additional control parameters",
    )

    class Config:
        schema_extra = {
            "example": {
                "input": [
                    {"source": "\u0928\u092e\u0938\u094d\u0924\u0947 \u0926\u0941\u0928\u093f\u092f\u093e"},
                    {"source": "Hello world"},
                ],
                "config": {"serviceId": "ai4bharat/indiclid"},
            }
        }


# ── Response models ─────────────────────────────────────────────────


class LanguagePrediction(BaseModel):
    """Language prediction result."""

    langCode: str = Field(..., description="ISO 639-3 language code (e.g., 'hin', 'eng', 'tam')")
    scriptCode: str = Field(..., description="ISO 15924 script code (e.g., 'Deva', 'Latn', 'Taml')")
    langScore: float = Field(..., description="Confidence score for the prediction (0.0 to 1.0)")
    language: str = Field(..., description="Full language name (e.g., 'Hindi', 'English')")


class LanguageDetectionOutput(BaseModel):
    """Output for a single text input."""

    source: str = Field(..., description="Source text")
    langPrediction: List[LanguagePrediction] = Field(
        ...,
        description="List of language predictions (typically top-1 or top-N)",
    )


class LanguageDetectionInferenceResponse(BaseModel):
    """Response model for language detection inference."""

    output: List[LanguageDetectionOutput] = Field(
        ...,
        description="Language detection results",
    )
    config: Optional[dict] = Field(None, description="Response configuration metadata")

    class Config:
        schema_extra = {
            "example": {
                "output": [
                    {
                        "source": "\u0928\u092e\u0938\u094d\u0924\u0947 \u0926\u0941\u0928\u093f\u092f\u093e",
                        "langPrediction": [
                            {
                                "langCode": "hin",
                                "scriptCode": "Deva",
                                "langScore": 0.98,
                                "language": "Hindi",
                            }
                        ],
                    },
                    {
                        "source": "Hello world",
                        "langPrediction": [
                            {
                                "langCode": "eng",
                                "scriptCode": "Latn",
                                "langScore": 0.99,
                                "language": "English",
                            }
                        ],
                    },
                ]
            }
        }
