"""
Pydantic models for ASR inference requests.

Adapted from Dhruva-Platform-2 ULCA schemas for ASR service.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, validator, Field, model_validator, HttpUrl


class AudioFormat(str, Enum):
    """Supported audio formats."""
    WAV = "wav"
    MP3 = "mp3"
    FLAC = "flac"
    OGG = "ogg"
    PCM = "pcm"


class TranscriptionFormat(str, Enum):
    """Supported transcription output formats."""
    TRANSCRIPT = "transcript"
    SRT = "srt"
    WEBVTT = "webvtt"


class AudioInput(BaseModel):
    """Audio input specification."""
    audioContent: Optional[str] = Field(None, description="Base64 encoded audio content")
    audioUri: Optional[HttpUrl] = Field(None, description="URL to audio file")
    
    @model_validator(mode='after')
    def validate_audio_input(self):
        """Ensure at least one of audioContent or audioUri is provided."""
        if not self.audioContent and not self.audioUri:
            raise ValueError('At least one of audioContent or audioUri must be provided')
        
        return self


class LanguageConfig(BaseModel):
    """Language configuration for ASR."""
    sourceLanguage: str = Field(..., description="Source language code (e.g., 'en', 'hi', 'ta')")
    sourceScriptCode: Optional[str] = Field(None, description="Script code if applicable")


class AudioConfig(BaseModel):
    """Audio configuration for processing."""
    language: LanguageConfig = Field(..., description="Language configuration")
    audioFormat: Optional[AudioFormat] = Field(None, description="Format of input audio")
    samplingRate: Optional[int] = Field(None, description="Sample rate in Hz")
    encoding: Optional[str] = Field("base64", description="Encoding type")


class ASRInferenceConfig(BaseModel):
    """Configuration for ASR inference."""
    # serviceId is optional to allow SMR to select a service when not provided
    serviceId: Optional[str] = Field(
        None,
        description=(
            "Identifier for ASR service/model. "
            "If not provided, SMR service will be called to select a serviceId."
        ),
    )
    language: LanguageConfig = Field(..., description="Language configuration")
    audioFormat: Optional[AudioFormat] = Field(None, description="Audio format")
    preProcessors: Optional[List[str]] = Field(None, description="List of preprocessors (e.g., ['vad', 'denoiser'])")
    postProcessors: Optional[List[str]] = Field(None, description="List of postprocessors (e.g., ['itn', 'punctuation'])")
    transcriptionFormat: TranscriptionFormat = Field(TranscriptionFormat.TRANSCRIPT, description="Output format")
    bestTokenCount: int = Field(0, description="Number of n-best tokens", ge=0, le=10)

    @validator("serviceId")
    def normalize_service_id(cls, v: Optional[str]) -> Optional[str]:
        """
        Normalize serviceId:
        - Allow None or empty string so SMR can resolve when missing
        - Strip whitespace when provided
        """
        if v is not None and v.strip():
            return v.strip()
        return None

    @validator('preProcessors')
    def normalize_and_validate_preprocessors(cls, v):
        """
        Normalize and validate preprocessor names.

        Note:
            The frontend currently sends "denoise" while the backend expects "denoiser".
            To remain backward compatible without forcing UI changes, we map "denoise"
            to "denoiser" here before validation.
        """
        if v is None:
            return v

        # Normalize known aliases
        normalized = []
        for processor in v:
            if processor == "denoise":
                normalized.append("denoiser")
            else:
                normalized.append(processor)

        valid_preprocessors = ["vad", "denoiser"]
        for processor in normalized:
            if processor not in valid_preprocessors:
                raise ValueError(
                    f"Invalid preprocessor: {processor}. Valid options: {valid_preprocessors}"
                )

        return normalized
    
    @validator('postProcessors')
    def validate_postprocessors(cls, v):
        """Validate postprocessor names."""
        if v is not None:
            valid_postprocessors = ["itn", "punctuation", "lm"]
            for processor in v:
                if processor not in valid_postprocessors:
                    raise ValueError(f"Invalid postprocessor: {processor}. Valid options: {valid_postprocessors}")
        return v


class ASRInferenceRequest(BaseModel):
    """Main ASR inference request model."""
    audio: List[AudioInput] = Field(..., description="List of audio inputs to process", min_items=1)
    config: ASRInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")
    
    @validator('audio')
    def validate_audio_list(cls, v):
        """Ensure at least one audio input is provided."""
        if not v or len(v) == 0:
            raise ValueError('At least one audio input is required')
        return v
    
    def dict(self, **kwargs):
        """
        Override dict() to exclude None values by default.

        If exclude_none is explicitly set to False by the caller (e.g., for SMR),
        respect that and return all fields including None.
        """
        if "exclude_none" in kwargs and kwargs["exclude_none"] is False:
            return super().dict(**kwargs)
        return super().dict(exclude_none=True, **kwargs)
