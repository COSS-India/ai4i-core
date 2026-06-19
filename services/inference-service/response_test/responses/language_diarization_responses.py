"""Pre-defined Language Diarization responses for response-size load testing.

Responses verified against the real dev instance output contract.
Each response mirrors the exact output of the language-diarization endpoint:
  "taskType"  — always "language-diarization"
  "output"    — list with one item containing:
      "total_segments"   — int, must equal len(segments)
      "segments"         — list of segment objects, each with:
          "start_time"   — float, segment start in seconds
          "end_time"     — float, segment end in seconds
          "duration"     — float, equals end_time - start_time
          "language"     — string, "code: Name" format (e.g. "hi: Hindi")
          "confidence"   — float 0.0–1.0
      "target_language"  — "all"
  "config"    — populated with serviceId (not null)
  smr_response is NOT present — the route does not include it

Unlike text language detection, the input is base64-encoded audio.
Payload size reflects base64 string length, which correlates with audio duration.

Three sizes are provided:
  SMALL_LANGUAGE_DIARIZATION_RESPONSE   — short audio clip (4 segments)
  MEDIUM_LANGUAGE_DIARIZATION_RESPONSE  — medium audio clip (7 segments)
  LARGE_LANGUAGE_DIARIZATION_RESPONSE   — long audio clip (11 segments, from real response)
"""

from typing import Any

_SERVICE_ID = "5d30f31a9653572878e91e954d038649"

SMALL_LANGUAGE_DIARIZATION_RESPONSE: dict[str, Any] = {
    "taskType": "language-diarization",
    "output": [
        {
            "total_segments": 4,
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 2.0,
                    "duration": 2.0,
                    "language": "hi: Hindi",
                    "confidence": 0.7832,
                },
                {
                    "start_time": 1.5,
                    "end_time": 3.5,
                    "duration": 2.0,
                    "language": "hi: Hindi",
                    "confidence": 0.8541,
                },
                {
                    "start_time": 3.0,
                    "end_time": 4.5,
                    "duration": 1.5,
                    "language": "ta: Tamil",
                    "confidence": 0.6123,
                },
                {
                    "start_time": 4.0,
                    "end_time": 5.0,
                    "duration": 1.0,
                    "language": "ta: Tamil",
                    "confidence": 0.5342,
                },
            ],
            "target_language": "all",
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
    },
}

MEDIUM_LANGUAGE_DIARIZATION_RESPONSE: dict[str, Any] = {
    "taskType": "language-diarization",
    "output": [
        {
            "total_segments": 7,
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 2.0,
                    "duration": 2.0,
                    "language": "hi: Hindi",
                    "confidence": 0.8234,
                },
                {
                    "start_time": 1.5,
                    "end_time": 3.5,
                    "duration": 2.0,
                    "language": "hi: Hindi",
                    "confidence": 0.7891,
                },
                {
                    "start_time": 3.0,
                    "end_time": 5.0,
                    "duration": 2.0,
                    "language": "ta: Tamil",
                    "confidence": 0.9123,
                },
                {
                    "start_time": 4.5,
                    "end_time": 6.5,
                    "duration": 2.0,
                    "language": "ml: Malayalam",
                    "confidence": 0.8765,
                },
                {
                    "start_time": 6.0,
                    "end_time": 8.0,
                    "duration": 2.0,
                    "language": "ml: Malayalam",
                    "confidence": 0.9432,
                },
                {
                    "start_time": 7.5,
                    "end_time": 9.5,
                    "duration": 2.0,
                    "language": "ta: Tamil",
                    "confidence": 0.7654,
                },
                {
                    "start_time": 9.0,
                    "end_time": 10.5,
                    "duration": 1.5,
                    "language": "hi: Hindi",
                    "confidence": 0.6789,
                },
            ],
            "target_language": "all",
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
    },
}

# LARGE response uses the exact data from the real dev instance.
LARGE_LANGUAGE_DIARIZATION_RESPONSE: dict[str, Any] = {
    "taskType": "language-diarization",
    "output": [
        {
            "total_segments": 11,
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 2.0,
                    "duration": 2.0,
                    "language": "ta: Tamil",
                    "confidence": 0.4775,
                },
                {
                    "start_time": 1.5,
                    "end_time": 3.5,
                    "duration": 2.0,
                    "language": "ta: Tamil",
                    "confidence": 0.68,
                },
                {
                    "start_time": 3.0,
                    "end_time": 5.0,
                    "duration": 2.0,
                    "language": "hi: Hindi",
                    "confidence": 0.6278,
                },
                {
                    "start_time": 4.5,
                    "end_time": 6.5,
                    "duration": 2.0,
                    "language": "hi: Hindi",
                    "confidence": 0.8821,
                },
                {
                    "start_time": 6.0,
                    "end_time": 8.0,
                    "duration": 2.0,
                    "language": "ur: Urdu",
                    "confidence": 0.9213,
                },
                {
                    "start_time": 7.5,
                    "end_time": 9.5,
                    "duration": 2.0,
                    "language": "ml: Malayalam",
                    "confidence": 0.9985,
                },
                {
                    "start_time": 9.0,
                    "end_time": 11.0,
                    "duration": 2.0,
                    "language": "ml: Malayalam",
                    "confidence": 0.9755,
                },
                {
                    "start_time": 10.5,
                    "end_time": 12.5,
                    "duration": 2.0,
                    "language": "ml: Malayalam",
                    "confidence": 1.0,
                },
                {
                    "start_time": 12.0,
                    "end_time": 14.0,
                    "duration": 2.0,
                    "language": "ta: Tamil",
                    "confidence": 0.8675,
                },
                {
                    "start_time": 13.5,
                    "end_time": 15.5,
                    "duration": 2.0,
                    "language": "ta: Tamil",
                    "confidence": 0.9968,
                },
                {
                    "start_time": 15.0,
                    "end_time": 16.85,
                    "duration": 1.85,
                    "language": "nn: Norwegian Nynorsk",
                    "confidence": 0.1881,
                },
            ],
            "target_language": "all",
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
    },
}
