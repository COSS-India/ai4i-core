"""
Models package for ASR Service.

Contains Pydantic models for request/response validation and SQLAlchemy models for database operations.
"""

# Import and re-export all model classes for easy access
from .asr_request import (
    ASRInferenceRequest,
    ASRInferenceConfig,
    AudioInput,
    AudioConfig,
    LanguageConfig,
    AudioFormat,
    TranscriptionFormat
)

from .asr_response import (
    ASRInferenceResponse,
    TranscriptOutput,
    NBestToken
)

from .database_models import (
    ASRRequestDB,
    ASRResultDB
)

from .auth_models import (
    UserDB,
    RoleDB,
    PermissionDB,
    ApiKeyDB,
    SessionDB
)

from .streaming_models import (
    StreamingConfig,
    StreamingAudioChunk,
    StreamingResponse,
    StreamingSessionState,
    StreamingError
)

__all__ = [
    # Request models
    "ASRInferenceRequest",
    "ASRInferenceConfig", 
    "AudioInput",
    "AudioConfig",
    "LanguageConfig",
    "AudioFormat",
    "TranscriptionFormat",
    
    # Response models
    "ASRInferenceResponse",
    "TranscriptOutput",
    "NBestToken",
    
    # Database models
    "ASRRequestDB",
    "ASRResultDB",
    
    # Auth models
    "UserDB",
    "RoleDB", 
    "PermissionDB",
    "ApiKeyDB",
    "SessionDB",
    
    # Streaming models
    "StreamingConfig",
    "StreamingAudioChunk", 
    "StreamingResponse",
    "StreamingSessionState",
    "StreamingError"
]
