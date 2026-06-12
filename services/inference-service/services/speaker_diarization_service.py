"""
SpeakerDiarizationTaskService — speaker diarization inference.

Fully adapter_config-driven on the v2 (JSONata) schema: AudioBase handles
base64-passthrough preprocessing and Triton I/O (and defaults num_speakers);
the v2 output_transform parses DIARIZATION_RESULT, sorts segments, dedups and
counts speakers, computes durations, and builds the envelope. No code here.

Triton tensor contract (adapter_config from MMS):
  Inputs:  AUDIO_DATA   (BYTES [1,1]) — base64 audio
           NUM_SPEAKERS (BYTES [1,1]) — expected speaker count, "" = auto
  Output:  DIARIZATION_RESULT (BYTES) — JSON blob
"""

from services.base.audio_base import AudioBase


class SpeakerDiarizationTaskService(AudioBase):
    """TaskService for Speaker Diarization inference (config-driven, v2)."""


__all__ = ["SpeakerDiarizationTaskService"]
