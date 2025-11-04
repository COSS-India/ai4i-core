"""
Pydantic models for ASR streaming functionality.

This module defines the data models used for WebSocket streaming communication
between clients and the ASR service, including configuration, audio chunks,
responses, and session state management.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, validator
import time
from uuid import UUID


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
    timestamp: float = Field(default_factory=time.time, description="Client-side timestamp")


class StreamingResponse(BaseModel):
    """Response sent from server to client."""
    
    transcript: str = Field(..., description="Partial or final transcript")
    isFinal: bool = Field(..., description="Whether this is final transcript for current segment")
    confidence: Optional[float] = Field(default=None, description="Confidence score")
    timestamp: float = Field(default_factory=time.time, description="Server-side timestamp")
    language: str = Field(..., description="Detected/configured language")


class StreamingError(BaseModel):
    """Error response sent from server to client."""
    
    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code (e.g., 'INVALID_CONFIG', 'INFERENCE_FAILED')")
    timestamp: float = Field(default_factory=time.time, description="Error timestamp")


@dataclass
class StreamingSessionState:
    """Session state for a streaming ASR connection.
    
    Using dataclass instead of Pydantic BaseModel for better performance
    during high-frequency operations like audio processing.
    """
    
    session_id: str
    buffer: bytes = field(default_factory=bytes)
    config: StreamingConfig = None
    api_key: Optional[str] = None
    user_id: Optional[int] = None
    api_key_id: Optional[int] = None
    run_inference_once_in_bytes: int = 0
    last_inference_position_in_bytes: int = 0
    historical_text: str = ""
    request_id: Optional[UUID] = None
    created_at: float = field(default_factory=time.time)
    
    def reset_buffer(self) -> None:
        """Reset audio buffer and inference position."""
        self.buffer = bytes()
        self.last_inference_position_in_bytes = 0
    
    def should_run_inference(self) -> bool:
        """Check if enough audio has accumulated to run inference."""
        if self.run_inference_once_in_bytes <= 0:
            return False
        return (len(self.buffer) - self.last_inference_position_in_bytes) >= self.run_inference_once_in_bytes
    
    def add_to_history(self, text: str) -> None:
        """Add text to historical transcript."""
        if text.strip():
            self.historical_text += text + '\n'
    
    def update_inference_position(self) -> None:
        """Update the last inference position to current buffer length."""
        self.last_inference_position_in_bytes = len(self.buffer)
