"""PII (Personally Identifiable Information) Detection and Redaction service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    """Input for PII detection task."""

    source: str = Field(..., description="Text to scan for PII")


class PIIConfig(BaseModel):
    """Configuration for PII detection inference."""

    service_id: str = Field(..., description="Service ID (required)")
    language: str = Field(..., description="Language code for PII detection")
    redaction_mode: Optional[str] = Field("mask", description="Redaction mode: mask, replace, remove")
    domains: Optional[List[str]] = Field(None, description="PII domains to detect (e.g., email, phone, ssn)")


class PIIInferenceRequest(BaseModel):
    """Request for PII detection inference."""

    input: List[TextInput] = Field(
        ..., min_items=1, max_items=20, description="Text inputs to scan for PII"
    )
    config: PIIConfig = Field(..., description="PII detection configuration")


class PIIEntity(BaseModel):
    """Detected PII entity."""

    entity_type: str = Field(..., description="PII type (e.g., EMAIL, PHONE, SSN, NAME)")
    start_pos: int = Field(..., description="Character start position")
    end_pos: int = Field(..., description="Character end position")
    text: str = Field(..., description="Original PII text")
    redacted_text: str = Field(..., description="Redacted PII text")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")


class PIIOutput(BaseModel):
    """Output from PII detection inference."""

    original_text: str = Field(..., description="Original input text")
    redacted_text: str = Field(..., description="Text with PII redacted")
    entities: List[PIIEntity] = Field(..., description="Detected PII entities")


class PIIInferenceResponse(BaseModel):
    """Response from PII detection inference."""

    output: List[PIIOutput] = Field(..., description="PII detection results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
