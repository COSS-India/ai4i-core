"""
OCR Response Models

Pydantic models for OCR inference responses, mirroring the style used
by ASR/TTS/NMT services while keeping a ULCA-like structure.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TextOutput(BaseModel):
    """Extracted text output for a single image input."""

    source: str = Field(..., description="Extracted text from the image")
    target: str = Field(
        "", description="Reserved for future use (kept for ULCA compatibility)"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class OCRInferenceResponse(BaseModel):
    """Main OCR inference response model."""

    output: List[TextOutput] = Field(
        ..., description="List of OCR results (one per image input)"
    )
    config: Optional[Dict[str, Any]] = Field(
        None, description="Response configuration metadata"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


