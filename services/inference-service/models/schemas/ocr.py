"""OCR (Optical Character Recognition) service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ImageInput(BaseModel):
    """Input for image-based OCR task."""

    model_config = ConfigDict(populate_by_name=True)

    image_content: Optional[str] = Field(
        None, alias="imageContent", description="Base64 encoded image data"
    )
    image_uri: Optional[str] = Field(
        None, alias="imageUri", description="HTTP URL to image file"
    )


class OCRConfig(BaseModel):
    """Configuration for OCR inference."""

    model_config = ConfigDict(populate_by_name=True)

    service_id: str = Field(
        ..., alias="serviceId", description="Service ID (required)"
    )
    language: Optional[str] = Field(None, description="Language hint for OCR")
    return_confidence: Optional[bool] = Field(
        False, alias="returnConfidence", description="Return confidence scores"
    )


class OCRInferenceRequest(BaseModel):
    """Request for OCR inference."""

    image: List[ImageInput] = Field(..., min_items=1, description="Image inputs to process")
    config: OCRConfig = Field(..., description="OCR configuration")


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
