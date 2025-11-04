"""
TTS Service Models Package

This package contains all Pydantic models and SQLAlchemy ORM models
for the TTS microservice.
"""

from models.tts_request import (
    TTSInferenceRequest,
    TTSInferenceConfig,
    TextInput,
    LanguageConfig,
    Gender,
    AudioFormat
)
from models.tts_response import (
    TTSInferenceResponse,
    AudioOutput,
    AudioConfig
)
from models.database_models import (
    TTSRequestDB,
    TTSResultDB
)
from models.auth_models import (
    UserDB,
    ApiKeyDB,
    SessionDB
)
from models.voice_models import (
    VoiceGender,
    VoiceAge,
    VoiceMetadata,
    VoiceListRequest,
    VoiceListResponse
)
from models.streaming_models import (
    StreamingTTSConfig,
    StreamingTextChunk,
    StreamingAudioResponse,
    StreamingTTSError,
    StreamingTTSSessionState
)

__all__ = [
    # Request models
    "TTSInferenceRequest",
    "TTSInferenceConfig", 
    "TextInput",
    "LanguageConfig",
    "Gender",
    "AudioFormat",
    # Response models
    "TTSInferenceResponse",
    "AudioOutput",
    "AudioConfig",
    # Database models
    "TTSRequestDB",
    "TTSResultDB",
    # Auth models
    "UserDB",
    "ApiKeyDB",
    "SessionDB",
    # Voice models
    "VoiceGender",
    "VoiceAge",
    "VoiceMetadata",
    "VoiceListRequest",
    "VoiceListResponse",
    # Streaming models
    "StreamingTTSConfig",
    "StreamingTextChunk",
    "StreamingAudioResponse",
    "StreamingTTSError",
    "StreamingTTSSessionState"
]
