"""Pre-defined Audio Language Detection responses for response-size load testing.

Responses verified against the real dev instance output contract.
Each response mirrors the exact output of the audio-lang-detection endpoint:
  "taskType"  — always "audio-lang-detection"
  "output"    — list with one item containing:
      "language_code"  — detected language as "code: Name" (e.g. "hi: Hindi")
      "confidence"     — float 0.0–1.0 (top prediction confidence)
      "all_scores"     — dict with:
          "predicted_language" — same as language_code
          "confidence"         — same as top-level confidence
          "top_scores"         — list of 5 floats (top-5 language probabilities)
  "config"    — populated with serviceId (not null)
  smr_response is NOT present — the route does not include it

Unlike text language detection, the input is base64-encoded audio.
Payload size reflects base64 string length, which correlates with audio duration.

Three sizes are provided:
  SMALL_AUDIO_LANG_DETECTION_RESPONSE   — short audio clip
  MEDIUM_AUDIO_LANG_DETECTION_RESPONSE  — medium audio clip
  LARGE_AUDIO_LANG_DETECTION_RESPONSE   — long audio clip
"""

from typing import Any

_SERVICE_ID = "356b2b50747f44aa2abed17cae94327c"

SMALL_AUDIO_LANG_DETECTION_RESPONSE: dict[str, Any] = {
    "taskType": "audio-lang-detection",
    "output": [
        {
            "language_code": "te: Telugu",
            "confidence": 0.6430134773254395,
            "all_scores": {
                "predicted_language": "te: Telugu",
                "confidence": 0.6430134773254395,
                "top_scores": [
                    0.6430134177207947,
                    0.12550882995128632,
                    0.06981785595417023,
                    0.058973148465156555,
                    0.028858909383416176,
                ],
            },
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
    },
}

MEDIUM_AUDIO_LANG_DETECTION_RESPONSE: dict[str, Any] = {
    "taskType": "audio-lang-detection",
    "output": [
        {
            "language_code": "hi: Hindi",
            "confidence": 0.7823415994644165,
            "all_scores": {
                "predicted_language": "hi: Hindi",
                "confidence": 0.7823415994644165,
                "top_scores": [
                    0.7823415994644165,
                    0.09812344610691071,
                    0.06234567165374756,
                    0.034291982650756836,
                    0.023097291588783264,
                ],
            },
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
    },
}

LARGE_AUDIO_LANG_DETECTION_RESPONSE: dict[str, Any] = {
    "taskType": "audio-lang-detection",
    "output": [
        {
            "language_code": "hi: Hindi",
            "confidence": 0.9156234860420227,
            "all_scores": {
                "predicted_language": "hi: Hindi",
                "confidence": 0.9156234860420227,
                "top_scores": [
                    0.9156234860420227,
                    0.04123456776142120,
                    0.02134567126631737,
                    0.01298765279352665,
                    0.00880862213671207,
                ],
            },
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
    },
}
