"""Triton-level stub responses for the TTS service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for a TTS
infer call.  The inference service reads ``outputs[0].data`` as the FP32 audio
samples array.

Payload size proxy is the length of the input text (characters).
Audio sample counts scale with text length:
  SMALL  — short phrase  → ~22050 samples (~1 s at 22050 Hz)
  MEDIUM — sentence      → ~88200 samples (~4 s)
  LARGE  — paragraph     → ~441000 samples (~20 s)

``data`` contains a 440 Hz sine wave at 0.3 amplitude so the inference service
produces valid, non-empty base64 audio instead of an empty WAV.
"""

import math
from typing import Any


def _sine_wave(n_samples: int, freq: float = 440.0, sample_rate: int = 22050) -> list:
    """Return n_samples FP32 values of a sine wave at freq Hz."""
    step = 2.0 * math.pi * freq / sample_rate
    return [round(math.sin(i * step) * 0.3, 6) for i in range(n_samples)]


SMALL_TTS_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "tts",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_GENERATED_AUDIO",
            "datatype": "FP32",
            "shape": [1, 22050],
            "data": _sine_wave(22050),
        }
    ],
}

MEDIUM_TTS_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "tts",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_GENERATED_AUDIO",
            "datatype": "FP32",
            "shape": [1, 88200],
            "data": _sine_wave(88200),
        }
    ],
}

LARGE_TTS_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "tts",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_GENERATED_AUDIO",
            "datatype": "FP32",
            "shape": [1, 441000],
            "data": _sine_wave(441000),
        }
    ],
}
