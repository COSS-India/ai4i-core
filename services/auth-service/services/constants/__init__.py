"""
Service name to resource name mapping constants.

This mapping converts service names (with hyphens, as used in API endpoints and permissions)
to resource names (with underscores, as used in Casbin permission checks).

Permissions in the database use hyphens (e.g., "audio-lang-detection.inference"),
but resource names for Casbin checking use underscores (e.g., "audio_lang_detection").
"""

# Map service names (with hyphens) to resource names (with underscores)
# Only services that need conversion are listed here
# Services without hyphens (asr, tts, nmt, etc.) don't need mapping
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
