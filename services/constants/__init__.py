"""
Constants package for all services.
"""
from .error_messages import *

# Service name to resource name mapping
# This mapping converts service names (with hyphens, as used in API endpoints and permissions)
# to resource names (with underscores, as used in Casbin permission checks).
# Permissions in the database use hyphens (e.g., "audio-lang-detection.inference"),
# but resource names for Casbin checking use underscores (e.g., "audio_lang_detection").
SERVICE_TO_RESOURCE_MAP = {
    'audio-lang-detection': 'audio_lang_detection',
    'language-detection': 'language_detection',
    'language-diarization': 'language_diarization',
    'speaker-diarization': 'speaker_diarization',
    # Note: 'model-management' keeps hyphens (no underscore conversion)
}

def get_resource_name(service_name: str) -> str:
    """
    Convert service name to resource name.
    
    Args:
        service_name: Service name (may have hyphens)
        
    Returns:
        Resource name (with underscores if mapping exists, otherwise unchanged)
    """
    return SERVICE_TO_RESOURCE_MAP.get(service_name, service_name)

__all__ = [
    # ASR Error Codes
    'LANGUAGE_NOT_SUPPORTED',
    'SERVICE_UNAVAILABLE',
    'PROCESSING_TIMEOUT',
    'QUOTA_EXCEEDED',
    'MODEL_UNAVAILABLE',
    'RATE_LIMIT_EXCEEDED',
    'POOR_AUDIO_QUALITY',
    'INVALID_REQUEST',
    'AUTH_FAILED',
    'TENANT_SUSPENDED',
    'NO_FILE_SELECTED',
    'UNSUPPORTED_FORMAT',
    'FILE_TOO_LARGE',
    'INVALID_FILE',
    'UPLOAD_FAILED',
    'AUDIO_TOO_SHORT',
    'AUDIO_TOO_LONG',
    'EMPTY_AUDIO_FILE',
    'UPLOAD_TIMEOUT',
    # ASR Error Messages
    'LANGUAGE_NOT_SUPPORTED_MESSAGE',
    'SERVICE_UNAVAILABLE_MESSAGE',
    'PROCESSING_TIMEOUT_MESSAGE',
    'QUOTA_EXCEEDED_MESSAGE',
    'MODEL_UNAVAILABLE_MESSAGE',
    'RATE_LIMIT_EXCEEDED_MESSAGE',
    'POOR_AUDIO_QUALITY_MESSAGE',
    'INVALID_REQUEST_MESSAGE',
    'AUTH_FAILED_MESSAGE',
    'TENANT_SUSPENDED_MESSAGE',
    'NO_FILE_SELECTED_MESSAGE',
    'UNSUPPORTED_FORMAT_MESSAGE',
    'FILE_TOO_LARGE_MESSAGE',
    'INVALID_FILE_MESSAGE',
    'UPLOAD_FAILED_MESSAGE',
    'AUDIO_TOO_SHORT_MESSAGE',
    'AUDIO_TOO_LONG_MESSAGE',
    'EMPTY_AUDIO_FILE_MESSAGE',
    'UPLOAD_TIMEOUT_MESSAGE',
    # Service name mapping
    'SERVICE_TO_RESOURCE_MAP',
    'get_resource_name',
]
