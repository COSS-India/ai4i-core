"""
TTS Inference Request and Response schemas.

Combined from models/tts_request.py and models/tts_response.py.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


# ── Enums ──

class Gender(str, Enum):
    """Voice gender options for TTS."""
    MALE = "male"
    FEMALE = "female"


class AudioFormat(str, Enum):
    """Supported audio output formats."""
    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"
    PCM = "pcm"


# ── Request schemas ──

class LanguageConfig(BaseModel):
    """Language configuration for TTS."""
    sourceLanguage: str = Field(..., description="Language code (e.g., 'en', 'hi', 'ta')")
    sourceScriptCode: Optional[str] = Field(None, description="Script code if applicable")

    @validator('sourceLanguage')
    def validate_language_code(cls, v):
        if not v or len(v) < 2 or len(v) > 3:
            raise ValueError('Language code must be 2-3 characters')
        return v


class TextInput(BaseModel):
    """Individual text input for TTS synthesis."""
    source: str = Field(..., description="Input text to synthesize")
    audioDuration: Optional[float] = Field(None, description="Desired audio duration in seconds (for precise timing)")

    @validator('source')
    def validate_source_text(cls, v):
        if v is None:
            return ""
        return v.strip() if isinstance(v, str) else ""


class TTSInferenceConfig(BaseModel):
    """Configuration for TTS inference."""
    serviceId: Optional[str] = Field(
        None,
        description=(
            "Identifier for TTS service/model. "
            "If not provided, SMR service will be called to select a serviceId."
        ),
    )
    language: LanguageConfig = Field(..., description="Language configuration")
    gender: Gender = Field(..., description="Voice gender (male/female)")
    audioFormat: AudioFormat = Field(AudioFormat.WAV, description="Output audio format")
    samplingRate: Optional[int] = Field(22050, description="Target sample rate in Hz")
    encoding: str = Field("base64", description="Output encoding")

    @validator("serviceId")
    def normalize_service_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            return v.strip()
        return None

    @validator('samplingRate')
    def validate_sampling_rate(cls, v):
        if v is not None and (v < 8000 or v > 48000):
            raise ValueError('Sampling rate must be between 8000 and 48000 Hz')
        return v


class TTSInferenceRequest(BaseModel):
    """Main TTS inference request model."""
    input: List[TextInput] = Field(..., description="List of text inputs to synthesize")
    config: TTSInferenceConfig = Field(..., description="Configuration for inference")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")

    @validator('input')
    def validate_input_list(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one text input is required')
        return v

    def dict(self, **kwargs):
        """Override dict() to exclude None values by default."""
        if "exclude_none" in kwargs and kwargs["exclude_none"] is False:
            return super().dict(**kwargs)
        return super().dict(exclude_none=True, **kwargs)


# ── Response schemas ──

class AudioOutput(BaseModel):
    """Audio output containing synthesized speech."""
    audioContent: str = Field(..., description="Base64-encoded audio data")
    audioUri: Optional[str] = Field(None, description="URL to audio file (if stored externally)")

    def dict(self, **kwargs):
        return super().dict(exclude_none=True, **kwargs)


class AudioConfig(BaseModel):
    """Audio configuration metadata for the response."""
    language: LanguageConfig = Field(..., description="Language configuration")
    audioFormat: AudioFormat = Field(..., description="Format of output audio")
    encoding: str = Field("base64", description="Encoding type")
    samplingRate: int = Field(..., description="Sample rate in Hz")
    audioDuration: Optional[float] = Field(None, description="Actual audio duration in seconds")


class TTSInferenceResponse(BaseModel):
    """Main TTS inference response model."""
    audio: List[AudioOutput] = Field(..., description="List of generated audio outputs (one per text input)")
    config: Optional[AudioConfig] = Field(None, description="Response configuration metadata")
    smr_response: Optional[Dict[str, Any]] = Field(
        None,
        description="SMR response metadata when Smart Model Routing is used",
    )

    def dict(self, **kwargs):
        if "exclude_none" in kwargs:
            return super().dict(**kwargs)
        return super().dict(exclude_none=True, **kwargs)
