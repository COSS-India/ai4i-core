"""
OCR Request Models

Pydantic models for OCR inference requests, inspired by ULCA schemas
and mirroring the naming style used by ASR/TTS/NMT services.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


class LanguageConfig(BaseModel):
    """Language configuration for OCR."""

    sourceLanguage: str = Field(
        ..., description="Source language code (e.g., 'en', 'hi', 'ta')"
    )
    sourceScriptCode: Optional[str] = Field(
        None, description="Script code if applicable (e.g., 'Deva', 'Latn')"
    )


class ImageInput(BaseModel):
    """Image input specification."""

    imageContent: Optional[str] = Field(
        None, description="Base64 encoded image content"
    )
    imageUri: Optional[HttpUrl] = Field(
        None, description="URL from which the image can be downloaded"
    )

    @model_validator(mode="after")
    def validate_image_input(self) -> "ImageInput":
        """Ensure at least one of imageContent or imageUri is provided."""
        if not self.imageContent and not self.imageUri:
            raise ValueError(
                "At least one of imageContent or imageUri must be provided"
            )
        return self


class OCRInferenceConfig(BaseModel):
    """Configuration for OCR inference."""

    serviceId: str = Field(
        ..., description="Identifier for OCR service/model (e.g., Surya OCR)"
    )
    language: LanguageConfig = Field(..., description="Language configuration")
    textDetection: Optional[bool] = Field(
        False,
        description=(
            "Whether to enable advanced text detection (bounding boxes, lines, etc.). "
            "Currently used mainly for logging/metrics."
        ),
    )


class OCRInferenceRequest(BaseModel):
    """Main OCR inference request model."""

    image: List[ImageInput] = Field(
        ..., description="List of images to process", min_items=1
    )
    config: OCRInferenceConfig = Field(
        ..., description="Configuration for OCR inference"
    )
    controlConfig: Optional[Dict[str, Any]] = Field(
        None, description="Additional control parameters (reserved for future use)"
    )

    @model_validator(mode="after")
    def validate_image_list(self) -> "OCRInferenceRequest":
        """Ensure at least one image is provided."""
        if not self.image:
            raise ValueError("At least one image is required")
        return self

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


