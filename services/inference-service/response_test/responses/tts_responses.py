"""Pre-defined TTS responses for response-size load testing.

Responses verified against the real dev instance output contract.
Each response mirrors the exact output of the TTS inference endpoint:
  "audio"       — list with one item containing:
      "audioContent"   — base64-encoded MP3 audio (placeholder bytes in this file)
      "audioUri"       — always null
      "audioDuration"  — float, duration of the generated audio in seconds
  "config"      — populated (not null), contains language, audioFormat, encoding,
                  samplingRate, and audioDuration
  "smr_response" — always null

Unlike other inference services, TTS uses the "audio" key instead of "output",
and config is fully populated rather than null.

Three sizes are provided, corresponding to short / medium / long input texts:
  SMALL_TTS_RESPONSE   — short phrase (~30 chars in)
  MEDIUM_TTS_RESPONSE  — a few sentences (~299 chars in)
  LARGE_TTS_RESPONSE   — a multi-sentence paragraph (~1056 chars in)
"""

from typing import Any

# Placeholder base64 audio content — replace with real MP3 base64 for integration runs.
# Lengths scale with audioDuration: more text → longer audio → more bytes.
_SMALL_AUDIO_CONTENT  = "AAAA" * 20    # 80-char placeholder
_MEDIUM_AUDIO_CONTENT = "AAAA" * 133   # 532-char placeholder
_LARGE_AUDIO_CONTENT  = "AAAA" * 500   # 2000-char placeholder


SMALL_TTS_RESPONSE: dict[str, Any] = {
    "audio": [
        {
            "audioContent": _SMALL_AUDIO_CONTENT,
            "audioUri": None,
            "audioDuration": 2.0448072562358279,
        }
    ],
    "config": {
        "language": {
            "sourceLanguage": "hi",
            "sourceScriptCode": None,
        },
        "audioFormat": "mp3",
        "encoding": "base64",
        "samplingRate": 22050,
        "audioDuration": 2.0448072562358279,
    },
    "smr_response": None,
}

MEDIUM_TTS_RESPONSE: dict[str, Any] = {
    "audio": [
        {
            "audioContent": _MEDIUM_AUDIO_CONTENT,
            "audioUri": None,
            "audioDuration": 16.534240362811914,
        }
    ],
    "config": {
        "language": {
            "sourceLanguage": "hi",
            "sourceScriptCode": None,
        },
        "audioFormat": "mp3",
        "encoding": "base64",
        "samplingRate": 22050,
        "audioDuration": 16.534240362811914,
    },
    "smr_response": None,
}

LARGE_TTS_RESPONSE: dict[str, Any] = {
    "audio": [
        {
            "audioContent": _LARGE_AUDIO_CONTENT,
            "audioUri": None,
            "audioDuration": 72.30158730158730,
        }
    ],
    "config": {
        "language": {
            "sourceLanguage": "hi",
            "sourceScriptCode": None,
        },
        "audioFormat": "mp3",
        "encoding": "base64",
        "samplingRate": 22050,
        "audioDuration": 72.30158730158730,
    },
    "smr_response": None,
}
