"""Triton-level stub responses for the TTS service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for a TTS
infer call.  The inference service reads ``outputs[0].data`` as the FP32 audio
samples array.

Payload size proxy is the length of the input text (characters).
Audio sample counts scale with text length:
  SMALL  — short phrase  → ~22050 samples (~1 s at 22050 Hz)
  MEDIUM — sentence      → ~88200 samples (~4 s)
  LARGE  — paragraph     → ~441000 samples (~20 s)

``data`` is an empty list in stubs — a real load test should populate it with
FP32 values or keep it empty and measure serialisation overhead only.
"""

from typing import Any

SMALL_TTS_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "tts",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_GENERATED_AUDIO",
            "datatype": "FP32",
            "shape": [1, 22050],
            "data": [],
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
            "data": [],
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
            "data": [],
        }
    ],
}
