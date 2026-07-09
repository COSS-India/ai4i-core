"""Triton-level stub responses for the Language Diarization service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for a
language-diarization infer call.  ``outputs[0].data[0][0]`` is a JSON string
containing ``segments`` and ``target_language``.

Payload size proxy is the length of the base64-encoded audio string.

Three sizes — segment count scales with audio duration:
  SMALL_LANG_DIAR_TRITON_RESPONSE   — 1 segment (short clip)
  MEDIUM_LANG_DIAR_TRITON_RESPONSE  — 2 segments
  LARGE_LANG_DIAR_TRITON_RESPONSE   — 5 segments (long mixed-language clip)
"""

import json
from typing import Any

_LANG_HI = _LANG_HI

SMALL_LANG_DIAR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "lang_diarization",
    "model_version": "1",
    "outputs": [
        {
            "name": "DIARIZATION_RESULT",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [
                [json.dumps({
                    "segments": [
                        {"start_time": 0.0, "end_time": 2.5, "duration": 2.5, "language": _LANG_HI, "confidence": 0.9312},
                    ],
                    "target_language": "",
                })]
            ],
        }
    ],
}

MEDIUM_LANG_DIAR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "lang_diarization",
    "model_version": "1",
    "outputs": [
        {
            "name": "DIARIZATION_RESULT",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [
                [json.dumps({
                    "segments": [
                        {"start_time": 0.0, "end_time": 2.5, "duration": 2.5, "language": _LANG_HI, "confidence": 0.9312},
                        {"start_time": 2.5, "end_time": 5.1, "duration": 2.6, "language": "en: English", "confidence": 0.8745},
                    ],
                    "target_language": "",
                })]
            ],
        }
    ],
}

LARGE_LANG_DIAR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "lang_diarization",
    "model_version": "1",
    "outputs": [
        {
            "name": "DIARIZATION_RESULT",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [
                [json.dumps({
                    "segments": [
                        {"start_time": 0.0,  "end_time": 2.5,  "duration": 2.5,  "language": _LANG_HI,   "confidence": 0.9312},
                        {"start_time": 2.5,  "end_time": 5.1,  "duration": 2.6,  "language": "en: English", "confidence": 0.8745},
                        {"start_time": 5.1,  "end_time": 7.8,  "duration": 2.7,  "language": _LANG_HI,   "confidence": 0.9023},
                        {"start_time": 7.8,  "end_time": 11.2, "duration": 3.4,  "language": "ta: Tamil",   "confidence": 0.8631},
                        {"start_time": 11.2, "end_time": 15.0, "duration": 3.8,  "language": _LANG_HI,   "confidence": 0.9187},
                    ],
                    "target_language": "",
                })]
            ],
        }
    ],
}
