"""
Audio model service stubs — future tasks (ALD, Speaker Diarization, Language Diarization).

ASR is fully implemented in services/asr_service.py (ASRTaskService).
Each stub here will be fleshed out in its own PR when that task is scheduled.
"""

from services.base.audio_base import AudioBase


class AudioLangDetectionDefaultModel(AudioBase):
    """
    Default Audio Language Detection model service.
    Will override: preprocess_input (base64 passthrough instead of float decode).
    """
    pass


class SpeakerDiarizationDefaultModel(AudioBase):
    """
    Default Speaker Diarization model service.
    Will override: preprocess_input (base64 passthrough),
                   postprocess_output (speaker segments schema),
                   _get_default_adapter_config.
    """
    pass


class LanguageDiarizationDefaultModel(AudioBase):
    """
    Default Language Diarization model service.
    Will override: preprocess_input (base64 passthrough),
                   postprocess_output (language segments schema),
                   _get_default_adapter_config.
    """
    pass
