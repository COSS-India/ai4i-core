"""Pydantic models for request/response validation and OpenAPI documentation."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Request Models ────────────────────────────────────────────────────────


class ProfileOptions(BaseModel):
    """Optional processing flags for profiling."""

    include_entities: bool = Field(
        default=True,
        description="Whether to extract named entities (slower but more detailed)",
    )
    include_language_detection: bool = Field(
        default=True,
        description="Whether to perform language detection",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"include_entities": True, "include_language_detection": True}
            ]
        }
    }


class ProfileRequest(BaseModel):
    """Request body for profiling a single text."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Text to profile. Must be 1-50,000 characters.",
        examples=["The patient was administered 500mg of amoxicillin for bacterial infection treatment."],
    )
    source_lang: Optional[str] = Field(
        default=None,
        pattern=r"^[a-z]{2}$",
        description="ISO 639-1 language code hint (optional, e.g., 'en', 'es').",
        examples=["en"],
    )
    options: ProfileOptions = Field(
        default_factory=ProfileOptions,
        description="Optional processing flags",
    )

    @field_validator("text")
    @classmethod
    def validate_text_content(cls, v: str) -> str:
        """
        Validate text has meaningful content.

        This validator:
        - Strips leading/trailing whitespace
        - Normalizes multiple consecutive spaces to single spaces
        - Preserves newlines and punctuation (they're valid content)
        - Requires at least 2 words of actual content
        - Accepts punctuation, numbers, and special characters

        Examples of valid inputs:
        - "Hello,   world!" (multiple spaces, punctuation)
        - "Patient has fever.  Temperature: 102°F." (numbers, special chars)
        - "Line one.\n\nLine two." (newlines)
        """
        # Strip leading/trailing whitespace
        stripped = v.strip()

        # Check if empty after stripping
        if not stripped:
            raise ValueError("Text must not be empty or whitespace-only")

        # Normalize multiple consecutive spaces to single space
        # This handles cases like "Hello,   world!" → "Hello, world!"
        normalized = " ".join(stripped.split())

        # Check minimum word count (at least 2 words)
        words = normalized.split()
        if len(words) < 2:
            raise ValueError("Text must contain at least 2 words")

        # Return the normalized text (spaces normalized, but newlines preserved in original)
        # We return the original stripped text to preserve formatting like newlines
        return stripped

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "The patient was administered 500mg of amoxicillin for bacterial infection treatment.",
                    "source_lang": "en",
                    "options": {
                        "include_entities": True,
                        "include_language_detection": True,
                    },
                }
            ]
        }
    }


class BatchProfileRequest(BaseModel):
    """Request body for profiling multiple texts."""

    texts: List[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of texts to profile (max 50)",
    )
    options: ProfileOptions = Field(
        default_factory=ProfileOptions,
        description="Optional processing flags applied to all texts",
    )

    @field_validator("texts")
    @classmethod
    def validate_texts(cls, v: List[str]) -> List[str]:
        """
        Validate each text in the batch.

        Applies the same validation as single text profiling:
        - Strips leading/trailing whitespace
        - Normalizes multiple consecutive spaces
        - Requires at least 2 words per text
        - Accepts punctuation, numbers, and special characters
        """
        if len(v) > 50:
            raise ValueError("Batch size cannot exceed 50 texts")

        for i, text in enumerate(v):
            # Strip leading/trailing whitespace
            stripped = text.strip()

            if not stripped:
                raise ValueError(f"Text at index {i} is empty")

            # Normalize multiple consecutive spaces to single space for word count check
            normalized = " ".join(stripped.split())
            words = normalized.split()

            if len(words) < 2:
                raise ValueError(f"Text at index {i} must contain at least 2 words")

        return v


# ── Response Models ───────────────────────────────────────────────────────


class LengthProfile(BaseModel):
    """Length-based features of the text."""

    char_count: int = Field(..., description="Total character count")
    word_count: int = Field(..., description="Total word count")
    sentence_count: int = Field(..., description="Number of sentences")
    avg_sentence_len: float = Field(..., description="Average words per sentence")
    bucket: str = Field(..., description="Length category: SHORT | MEDIUM | LONG")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "char_count": 77,
                    "word_count": 12,
                    "sentence_count": 1,
                    "avg_sentence_len": 12.0,
                    "bucket": "SHORT",
                }
            ]
        }
    }


class LanguageProfile(BaseModel):
    """Language detection results."""

    primary: str = Field(..., description="Primary language (ISO 639-1 code)")
    num_languages: int = Field(..., description="Number of distinct languages detected")
    mix_ratio: float = Field(
        ...,
        description="Language mixing ratio (0.0 = monolingual, 1.0 = fully mixed)",
    )
    language_switches: int = Field(
        ..., description="Number of language transitions"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "primary": "en",
                    "num_languages": 1,
                    "mix_ratio": 0.0,
                    "language_switches": 0,
                }
            ]
        }
    }


class DomainPrediction(BaseModel):
    """Single domain prediction with confidence."""

    label: str = Field(..., description="Domain label")
    confidence: float = Field(..., description="Prediction confidence (0.0-1.0)")


class DomainProfile(BaseModel):
    """Domain classification results."""

    label: str = Field(..., description="Predicted domain")
    confidence: float = Field(..., description="Confidence score (0.0-1.0)")
    top_3: List[DomainPrediction] = Field(
        ..., description="Top 3 domain predictions with confidence scores"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "medical",
                    "confidence": 0.94,
                    "top_3": [
                        {"label": "medical", "confidence": 0.94},
                        {"label": "technical", "confidence": 0.03},
                        {"label": "general", "confidence": 0.02},
                    ],
                }
            ]
        }
    }


class StructureProfile(BaseModel):
    """Structural and entity-based features."""

    entity_density: float = Field(..., description="Named entities per word")
    terminology_density: float = Field(..., description="Rare/technical words ratio")
    numeric_density: float = Field(..., description="Numeric character ratio")
    entity_types: Dict[str, int] = Field(
        ..., description="Count of each entity type (e.g., PERSON, ORG)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "entity_density": 0.17,
                    "terminology_density": 0.25,
                    "numeric_density": 0.08,
                    "entity_types": {"QUANTITY": 1, "PRODUCT": 1},
                }
            ]
        }
    }


class ScoresProfile(BaseModel):
    """Complexity scores and feature contributions."""

    complexity_score: float = Field(
        ..., description="Overall complexity score (0.0-1.0)"
    )
    complexity_level: str = Field(
        ..., description="Complexity bucket: LOW | HIGH (score < 0.5 = LOW, >= 0.5 = HIGH)"
    )
    feature_contributions: Dict[str, float] = Field(
        ..., description="Top feature contributions to complexity score"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "complexity_score": 0.62,
                    "complexity_level": "HIGH",  # >= 0.5
                    "feature_contributions": {
                        "terminology_density": 0.18,
                        "entity_density": 0.15,
                        "avg_sentence_len": 0.12,
                    },
                },
                {
                    "complexity_score": 0.35,
                    "complexity_level": "LOW",  # < 0.5
                    "feature_contributions": {
                        "word_length": 0.12,
                        "lexical_diversity": 0.10,
                        "sentence_length": 0.08,
                    },
                }
            ]
        }
    }


class ProfileResult(BaseModel):
    """Complete profile result for a single text."""

    length: LengthProfile
    language: LanguageProfile
    domain: DomainProfile
    structure: StructureProfile
    scores: ScoresProfile


class ResponseMetadata(BaseModel):
    """Metadata about the profiling operation."""

    model_version: str = Field(..., description="Model version used for profiling")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    timestamp: datetime = Field(..., description="Response timestamp (ISO 8601)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model_version": "1.0.0",
                    "processing_time_ms": 23,
                    "timestamp": "2026-02-08T14:30:00.123Z",
                }
            ]
        }
    }


class ProfileResponse(BaseModel):
    """Complete response for a single profile request."""

    request_id: str = Field(..., description="Unique request identifier")
    profile: ProfileResult = Field(..., description="Profiling results")
    metadata: ResponseMetadata = Field(..., description="Response metadata")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "request_id": "req_a1b2c3d4",
                    "profile": {
                        "length": {
                            "char_count": 77,
                            "word_count": 12,
                            "sentence_count": 1,
                            "avg_sentence_len": 12.0,
                            "bucket": "SHORT",
                        },
                        "language": {
                            "primary": "en",
                            "num_languages": 1,
                            "mix_ratio": 0.0,
                            "language_switches": 0,
                        },
                        "domain": {
                            "label": "medical",
                            "confidence": 0.94,
                            "top_3": [
                                {"label": "medical", "confidence": 0.94},
                                {"label": "technical", "confidence": 0.03},
                                {"label": "general", "confidence": 0.02},
                            ],
                        },
                        "structure": {
                            "entity_density": 0.17,
                            "terminology_density": 0.25,
                            "numeric_density": 0.08,
                            "entity_types": {"QUANTITY": 1, "PRODUCT": 1},
                        },
                        "scores": {
                            "complexity_score": 0.62,
                            "complexity_level": "HIGH",
                            "feature_contributions": {
                                "terminology_density": 0.18,
                                "entity_density": 0.15,
                                "avg_sentence_len": 0.12,
                            },
                        },
                    },
                    "metadata": {
                        "model_version": "1.0.0",
                        "processing_time_ms": 23,
                        "timestamp": "2026-02-08T14:30:00.123Z",
                    },
                }
            ]
        }
    }


class BatchProfileResponse(BaseModel):
    """Response for batch profile requests."""

    request_id: str = Field(..., description="Unique request identifier")
    profiles: List[ProfileResult] = Field(..., description="List of profile results")
    metadata: ResponseMetadata = Field(..., description="Response metadata")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    models_loaded: bool = Field(..., description="Whether models are loaded")
    timestamp: datetime = Field(..., description="Check timestamp")


class InfoResponse(BaseModel):
    """Service information response."""

    service_name: str
    service_version: str
    model_version: str
    uptime_seconds: float
    models_loaded: bool

