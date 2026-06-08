"""Audio Language Detection TaskService."""

from services.base.audio_base import AudioBase


class AudioLanguageDetectionTaskService(AudioBase):
    """
    TaskService for Audio Language Detection inference.

    Fully adapter_config-driven: AudioBase handles base64-passthrough
    preprocessing and Triton I/O; the adapter parses ALL_SCORES via
    transform "json_parse" and the response envelope declares
    task_type + config_keys ["serviceId"]. The base default
    postprocess_output applies that shaping — no code here.
    """


__all__ = ["AudioLanguageDetectionTaskService"]
