"""
TTS Service Services Package

This package contains all service classes for business logic.
"""

from services.tts_service import TTSService
from services.audio_service import AudioService
from services.text_service import TextService
from services.voice_service import VoiceService

# Try to import streaming service, but make it optional
try:
    from services.streaming_service import StreamingTTSService
    __all__ = [
        "TTSService",
        "AudioService",
        "TextService",
        "VoiceService",
        "StreamingTTSService"
    ]
except ImportError:
    # If streaming service can't be imported (missing dependencies), exclude it
    __all__ = [
        "TTSService",
        "AudioService",
        "TextService",
        "VoiceService"
    ]
