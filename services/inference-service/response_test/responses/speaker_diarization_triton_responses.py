"""Triton-level stub responses for the Speaker Diarization service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for a
speaker-diarization infer call.  ``outputs[0].data[0]`` is a JSON string
containing ``total_segments``, ``num_speakers``, ``speakers``, and ``segments``.

Payload size proxy is the length of the base64-encoded audio string.

Three sizes — speaker/segment count scales with audio duration:
  SMALL_SD_TRITON_RESPONSE   — 1 speaker, 1 segment (short clip)
  MEDIUM_SD_TRITON_RESPONSE  — 2 speakers, 3 segments
  LARGE_SD_TRITON_RESPONSE   — 3 speakers, 7 segments (long clip)
"""

import json
from typing import Any

SMALL_SD_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "speaker_diarization",
    "model_version": "1",
    "outputs": [
        {
            "name": "DIARIZATION_RESULT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                json.dumps({
                    "total_segments": 1,
                    "num_speakers": 1,
                    "speakers": ["SPEAKER_00"],
                    "segments": [
                        {"start_time": 0.0, "end_time": 3.2, "duration": 3.2, "speaker": "SPEAKER_00"},
                    ],
                })
            ],
        }
    ],
}

MEDIUM_SD_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "speaker_diarization",
    "model_version": "1",
    "outputs": [
        {
            "name": "DIARIZATION_RESULT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                json.dumps({
                    "total_segments": 3,
                    "num_speakers": 2,
                    "speakers": ["SPEAKER_00", "SPEAKER_01"],
                    "segments": [
                        {"start_time": 0.0, "end_time": 3.2, "duration": 3.2, "speaker": "SPEAKER_00"},
                        {"start_time": 3.2, "end_time": 6.7, "duration": 3.5, "speaker": "SPEAKER_01"},
                        {"start_time": 6.7, "end_time": 9.5, "duration": 2.8, "speaker": "SPEAKER_00"},
                    ],
                })
            ],
        }
    ],
}

LARGE_SD_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "speaker_diarization",
    "model_version": "1",
    "outputs": [
        {
            "name": "DIARIZATION_RESULT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                json.dumps({
                    "total_segments": 7,
                    "num_speakers": 3,
                    "speakers": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"],
                    "segments": [
                        {"start_time": 0.0,  "end_time": 3.2,  "duration": 3.2, "speaker": "SPEAKER_00"},
                        {"start_time": 3.2,  "end_time": 6.7,  "duration": 3.5, "speaker": "SPEAKER_01"},
                        {"start_time": 6.7,  "end_time": 9.5,  "duration": 2.8, "speaker": "SPEAKER_00"},
                        {"start_time": 9.5,  "end_time": 13.1, "duration": 3.6, "speaker": "SPEAKER_02"},
                        {"start_time": 13.1, "end_time": 16.4, "duration": 3.3, "speaker": "SPEAKER_01"},
                        {"start_time": 16.4, "end_time": 20.0, "duration": 3.6, "speaker": "SPEAKER_00"},
                        {"start_time": 20.0, "end_time": 23.8, "duration": 3.8, "speaker": "SPEAKER_02"},
                    ],
                })
            ],
        }
    ],
}
