"""Pre-defined Speaker Diarization responses for response-size load testing.

Responses verified against the real dev instance output contract.
Each response mirrors the exact output of the speaker-diarization endpoint:
  "taskType"  — always "speaker-diarization"
  "output"    — list with one item containing:
      "total_segments"  — int, must equal len(segments)
      "num_speakers"    — int, must equal len(speakers)
      "speakers"        — list of speaker ID strings (e.g. ["SPEAKER_00", "SPEAKER_01"])
      "segments"        — list of segment objects, each with:
          "start_time"  — float, segment start in seconds
          "end_time"    — float, segment end in seconds
          "duration"    — float, equals end_time - start_time
          "speaker"     — string, one of the IDs in speakers list
  "config"    — populated with serviceId (not null); language is null
  smr_response is NOT present — the route does not include it

Unlike Language Diarization, segments carry "speaker" (not "language" or
"confidence"), and config includes a "language" field that is null.

Three sizes are provided:
  SMALL_SPEAKER_DIARIZATION_RESPONSE   — short audio clip (4 segments, 2 speakers)
  MEDIUM_SPEAKER_DIARIZATION_RESPONSE  — medium audio clip (8 segments, 3 speakers)
  LARGE_SPEAKER_DIARIZATION_RESPONSE   — long audio clip (12 segments, 3 speakers)
"""

from typing import Any

_SERVICE_ID = "a9efafbfc2021f9a34dd201eab8f5687"

SMALL_SPEAKER_DIARIZATION_RESPONSE: dict[str, Any] = {
    "taskType": "speaker-diarization",
    "output": [
        {
            "total_segments": 4,
            "num_speakers": 2,
            "speakers": ["SPEAKER_00", "SPEAKER_01"],
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 2.5,
                    "duration": 2.5,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 2.5,
                    "end_time": 4.2,
                    "duration": 1.7,
                    "speaker": "SPEAKER_01",
                },
                {
                    "start_time": 4.2,
                    "end_time": 6.0,
                    "duration": 1.8,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 6.0,
                    "end_time": 8.0,
                    "duration": 2.0,
                    "speaker": "SPEAKER_01",
                },
            ],
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
        "language": None,
    },
}

MEDIUM_SPEAKER_DIARIZATION_RESPONSE: dict[str, Any] = {
    "taskType": "speaker-diarization",
    "output": [
        {
            "total_segments": 8,
            "num_speakers": 3,
            "speakers": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"],
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 2.3,
                    "duration": 2.3,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 2.3,
                    "end_time": 4.8,
                    "duration": 2.5,
                    "speaker": "SPEAKER_01",
                },
                {
                    "start_time": 4.8,
                    "end_time": 6.5,
                    "duration": 1.7,
                    "speaker": "SPEAKER_02",
                },
                {
                    "start_time": 6.5,
                    "end_time": 9.0,
                    "duration": 2.5,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 9.0,
                    "end_time": 11.2,
                    "duration": 2.2,
                    "speaker": "SPEAKER_01",
                },
                {
                    "start_time": 11.2,
                    "end_time": 13.0,
                    "duration": 1.8,
                    "speaker": "SPEAKER_02",
                },
                {
                    "start_time": 13.0,
                    "end_time": 15.5,
                    "duration": 2.5,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 15.5,
                    "end_time": 17.8,
                    "duration": 2.3,
                    "speaker": "SPEAKER_01",
                },
            ],
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
        "language": None,
    },
}

LARGE_SPEAKER_DIARIZATION_RESPONSE: dict[str, Any] = {
    "taskType": "speaker-diarization",
    "output": [
        {
            "total_segments": 12,
            "num_speakers": 3,
            "speakers": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"],
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 3.1,
                    "duration": 3.1,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 3.1,
                    "end_time": 5.8,
                    "duration": 2.7,
                    "speaker": "SPEAKER_01",
                },
                {
                    "start_time": 5.8,
                    "end_time": 8.0,
                    "duration": 2.2,
                    "speaker": "SPEAKER_02",
                },
                {
                    "start_time": 8.0,
                    "end_time": 10.5,
                    "duration": 2.5,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 10.5,
                    "end_time": 13.2,
                    "duration": 2.7,
                    "speaker": "SPEAKER_01",
                },
                {
                    "start_time": 13.2,
                    "end_time": 15.6,
                    "duration": 2.4,
                    "speaker": "SPEAKER_02",
                },
                {
                    "start_time": 15.6,
                    "end_time": 18.0,
                    "duration": 2.4,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 18.0,
                    "end_time": 20.3,
                    "duration": 2.3,
                    "speaker": "SPEAKER_01",
                },
                {
                    "start_time": 20.3,
                    "end_time": 22.5,
                    "duration": 2.2,
                    "speaker": "SPEAKER_00",
                },
                {
                    "start_time": 22.5,
                    "end_time": 25.0,
                    "duration": 2.5,
                    "speaker": "SPEAKER_02",
                },
                {
                    "start_time": 25.0,
                    "end_time": 27.4,
                    "duration": 2.4,
                    "speaker": "SPEAKER_01",
                },
                {
                    "start_time": 27.4,
                    "end_time": 29.85,
                    "duration": 2.45,
                    "speaker": "SPEAKER_00",
                },
            ],
        }
    ],
    "config": {
        "serviceId": _SERVICE_ID,
        "language": None,
    },
}
