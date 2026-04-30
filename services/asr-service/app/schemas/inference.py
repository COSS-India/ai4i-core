"""
Pydantic models for ASR inference requests and responses.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, validator, Field, model_validator, HttpUrl


# ── Request Models ──


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
        """Normalize serviceId: allow None/empty for SMR resolution, strip whitespace."""
        if v is not None and v.strip():
            return v.strip()
        return None

    @validator('preProcessors')
    def normalize_and_validate_preprocessors(cls, v):
        """Normalize and validate preprocessor names (maps 'denoise' -> 'denoiser')."""
        if v is None:
            return v

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
        """Override dict() to exclude None values by default."""
        if "exclude_none" in kwargs and kwargs["exclude_none"] is False:
            return super().dict(**kwargs)
        return super().dict(exclude_none=True, **kwargs)


# ── Response Models ──


class NBestToken(BaseModel):
    """N-best token alternative with confidence scores."""
    word: str = Field(..., description="The word/token")
    tokens: List[Dict[str, float]] = Field(..., description="List of alternative tokens with scores")


class TranscriptOutput(BaseModel):
    """Transcription output for a single audio input."""
    source: str = Field(..., description="The transcribed text")
    nBestTokens: Optional[List[NBestToken]] = Field(None, description="N-best token alternatives (if requested)")

    def dict(self, **kwargs):
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class ASRInferenceResponse(BaseModel):
    """Main ASR inference response model."""
    output: List[TranscriptOutput] = Field(..., description="List of transcription results (one per audio input)")
    config: Optional[Dict[str, Any]] = Field(None, description="Response configuration metadata")
    # SMR response if SMR was used to resolve serviceId or policies
    smr_response: Optional[Dict[str, Any]] = Field(
        None,
        description="SMR response metadata when Smart Model Routing is used",
    )

    def dict(self, **kwargs):
        """Override dict() to exclude None values by default, but allow explicit control."""
        if "exclude_none" in kwargs:
            return super().dict(**kwargs)
        return super().dict(exclude_none=True, **kwargs)


# ── Streaming Models ──


class StreamingConfig(BaseModel):
    """Configuration for streaming ASR session."""
    serviceId: str = Field(..., description="ASR model identifier")
    language: str = Field(..., description="Language code (e.g., 'en', 'hi')")
    samplingRate: int = Field(default=16000, description="Audio sample rate in Hz")
    audioFormat: str = Field(default="pcm", description="Format of streaming audio")
    responseFrequencyInMs: int = Field(default=2000, description="How often to emit partial transcripts (ms)")
    preProcessors: Optional[List[str]] = Field(default=None, description="Preprocessors like ['vad']")
    postProcessors: Optional[List[str]] = Field(default=None, description="Postprocessors like ['itn', 'punctuation']")
    enableVAD: bool = Field(default=True, description="Enable VAD-based chunking")

    @validator('language')
    def validate_language(cls, v):
        if not v or len(v) < 2:
            raise ValueError('Language code must be at least 2 characters')
        return v.lower()

    @validator('samplingRate')
    def validate_sampling_rate(cls, v):
        if not 8000 <= v <= 48000:
            raise ValueError('Sampling rate must be between 8000 and 48000 Hz')
        return v

    @validator('responseFrequencyInMs')
    def validate_response_frequency(cls, v):
        if v < 100:
            raise ValueError('Response frequency must be at least 100ms')
        return v


class StreamingAudioChunk(BaseModel):
    """Audio chunk sent from client to server."""
    audioContent: bytes = Field(..., description="Raw PCM audio bytes")
    isSpeaking: bool = Field(..., description="Whether user is currently speaking (for VAD)")
    timestamp: float = Field(default_factory=__import__('time').time, description="Client-side timestamp")


class StreamingResponse(BaseModel):
    """Response sent from server to client."""
    transcript: str = Field(..., description="Partial or final transcript")
    isFinal: bool = Field(..., description="Whether this is final transcript for current segment")
    confidence: Optional[float] = Field(default=None, description="Confidence score")
    timestamp: float = Field(default_factory=__import__('time').time, description="Server-side timestamp")
    language: str = Field(..., description="Detected/configured language")


class StreamingError(BaseModel):
    """Error response sent from server to client."""
    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code")
    timestamp: float = Field(default_factory=__import__('time').time, description="Error timestamp")
