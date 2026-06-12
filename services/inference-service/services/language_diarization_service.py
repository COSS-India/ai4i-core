"""Language Diarization TaskService."""

from services.base.audio_base import AudioBase


class LanguageDiarizationTaskService(AudioBase):
    """
    TaskService for Language Diarization inference (config-driven).

    AudioBase handles base64-passthrough preprocessing and Triton I/O. The
    adapter_config's LANGUAGE input declares value "" so an absent
    config.targetLanguage means "all languages"; the output_transform parses
    DIARIZATION_RESULT and builds the envelope. No code here.

    Triton tensor contract (adapter_config from MMS):
      Inputs:  AUDIO_DATA (BYTES [1,1]) — base64 audio
               LANGUAGE   (BYTES [1,1]) — target language code, "" = all
      Output:  DIARIZATION_RESULT (BYTES) — JSON blob
    """


__all__ = ["LanguageDiarizationTaskService"]
