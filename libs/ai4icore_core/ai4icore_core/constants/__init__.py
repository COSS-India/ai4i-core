"""
ai4icore_constants — Pure static data: error codes, error messages, service maps.

NO behavior, NO exceptions, NO FastAPI dependency.
Exceptions live in ai4icore_exceptions.
"""
from .error_messages import *

# Service name to resource name mapping
SERVICE_TO_RESOURCE_MAP = {
    'audio-lang-detection': 'audio_lang_detection',
    'language-detection': 'language_detection',
    'language-diarization': 'language_diarization',
    'speaker-diarization': 'speaker_diarization',
}

def get_resource_name(service_name: str) -> str:
    """Convert service name (hyphens) to resource name (underscores)."""
    return SERVICE_TO_RESOURCE_MAP.get(service_name, service_name)
