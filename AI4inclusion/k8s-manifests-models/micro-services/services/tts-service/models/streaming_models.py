from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, validator
import time


class StreamingTTSConfig(BaseModel):
    """TTS streaming configuration."""
    serviceId: str
    voice_id: str
    language: str
    gender: str
    samplingRate: int = 22050
    audioFormat: str = "wav"
    responseFrequencyInMs: int = 2000
    encoding: str = "base64"
    enableChunking: bool = True

    @validator('language')
    def validate_language(cls, v):
        if not v or len(v) < 2 or len(v) > 3:
            raise ValueError('Language code must be 2-3 characters')
        return v

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


class StreamingTextChunk(BaseModel):
    """Text chunk for TTS streaming."""
    text: str
    isFinal: bool
    timestamp: float

    @validator('text')
    def validate_text(cls, v):
        if not v.strip():
            raise ValueError('Text cannot be empty')
        if len(v) > 5000:
            raise ValueError('Text cannot exceed 5000 characters')
        return v


class StreamingAudioResponse(BaseModel):
    """Audio response for TTS streaming."""
    audioContent: str
    isFinal: bool
    duration: Optional[float] = None
    timestamp: float
    format: str


class StreamingTTSError(BaseModel):
    """Error response for TTS streaming."""
    error: str
    code: str
    timestamp: float


@dataclass
class StreamingTTSSessionState:
    """Session state for TTS streaming."""
    session_id: str
    config: StreamingTTSConfig
    text_buffer: str = ""
    api_key: Optional[str] = None
    user_id: Optional[int] = None
    api_key_id: Optional[int] = None
    request_id: Optional[str] = None
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def reset_buffer(self) -> None:
        """Reset the text buffer."""
        self.text_buffer = ""

    def add_text(self, text: str) -> None:
        """Add text to the buffer."""
        self.text_buffer += text

    def get_text_chunks(self, max_length: int = 400) -> List[str]:
        """Get text chunks for processing."""
        if not self.text_buffer:
            return []
        
        if len(self.text_buffer) <= max_length:
            return [self.text_buffer]
        
        chunks = []
        text = self.text_buffer
        while len(text) > max_length:
            # Find a good breaking point (space or punctuation)
            break_point = max_length
            for i in range(max_length - 1, max_length // 2, -1):
                if text[i] in ' \n\t.,!?;:':
                    break_point = i + 1
                    break
            
            chunks.append(text[:break_point].strip())
            text = text[break_point:].strip()
        
        if text:
            chunks.append(text)
        
        return chunks
