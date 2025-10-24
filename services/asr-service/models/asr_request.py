"""
Pydantic models for ASR inference requests.

Adapted from Dhruva-Platform-2 ULCA schemas for ASR service.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, HttpUrl, validator, Field, model_validator


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
    serviceId: str = Field(..., description="Identifier for ASR service/model")
    language: LanguageConfig = Field(..., description="Language configuration")
    audioFormat: Optional[AudioFormat] = Field(None, description="Audio format")
    preProcessors: Optional[List[str]] = Field(None, description="List of preprocessors (e.g., ['vad', 'denoiser'])")
    postProcessors: Optional[List[str]] = Field(None, description="List of postprocessors (e.g., ['itn', 'punctuation'])")
    transcriptionFormat: TranscriptionFormat = Field(TranscriptionFormat.TRANSCRIPT, description="Output format")
    bestTokenCount: int = Field(0, description="Number of n-best tokens", ge=0, le=10)
    
    @validator('preProcessors')
    def validate_preprocessors(cls, v):
        """Validate preprocessor names."""
        if v is not None:
            valid_preprocessors = ["vad", "denoiser"]
            for processor in v:
                if processor not in valid_preprocessors:
                    raise ValueError(f"Invalid preprocessor: {processor}. Valid options: {valid_preprocessors}")
        return v
    
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
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)
