"""OCR (Optical Character Recognition) service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
class OCROutput(BaseModel):
    """Output from OCR inference."""

    text: str = Field(..., description="Extracted text from image")
    layout: Optional[Dict[str, Any]] = Field(None, description="Layout/bounding box information")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")


class OCRInferenceResponse(BaseModel):
    """Response from OCR inference."""

    output: List[OCROutput] = Field(..., description="OCR results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
