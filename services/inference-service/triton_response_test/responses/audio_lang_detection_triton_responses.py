"""Triton-level stub responses for the Audio Language Detection service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for an ALD
infer call.  Three output tensors: LANGUAGE_CODE, CONFIDENCE, ALL_SCORES.

Payload size proxy is the length of the base64-encoded audio string.

Three sizes:
  SMALL_ALD_TRITON_RESPONSE   — short audio clip  (< 200 chars of base64)
  MEDIUM_ALD_TRITON_RESPONSE  — medium clip        (200–999 chars)
  LARGE_ALD_TRITON_RESPONSE   — long clip          (>= 1000 chars)
"""

import json
from typing import Any

_LANG_TA = _LANG_TA
_LANG_HI = _LANG_HI

SMALL_ALD_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ald",
    "model_version": "1",
    "outputs": [
        {
            "name": "LANGUAGE_CODE",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [[_LANG_TA]],
        },
        {
            "name": "CONFIDENCE",
            "shape": [1, 1],
            "datatype": "FP32",
            "data": [[0.9712]],
        },
        {
            "name": "ALL_SCORES",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [
                [json.dumps({
                    "predicted_language": _LANG_TA,
                    "confidence": 0.9712,
                    "top_scores": [0.9712, 0.0183, 0.0065, 0.0024, 0.0016],
                })]
            ],
        },
    ],
}

MEDIUM_ALD_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ald",
    "model_version": "1",
    "outputs": [
        {
            "name": "LANGUAGE_CODE",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [[_LANG_HI]],
        },
        {
            "name": "CONFIDENCE",
            "shape": [1, 1],
            "datatype": "FP32",
            "data": [[0.9867]],
        },
        {
            "name": "ALL_SCORES",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [
                [json.dumps({
                    "predicted_language": _LANG_HI,
                    "confidence": 0.9867,
                    "top_scores": [0.9867, 0.0091, 0.0024, 0.0012, 0.0006],
                })]
            ],
        },
    ],
}

LARGE_ALD_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ald",
    "model_version": "1",
    "outputs": [
        {
            "name": "LANGUAGE_CODE",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [[_LANG_TA]],
        },
        {
            "name": "CONFIDENCE",
            "shape": [1, 1],
            "datatype": "FP32",
            "data": [[0.999923586845398]],
        },
        {
            "name": "ALL_SCORES",
            "shape": [1, 1],
            "datatype": "BYTES",
            "data": [
                [json.dumps({
                    "predicted_language": _LANG_TA,
                    "confidence": 0.999923586845398,
                    "top_scores": [
                        0.999923586845398,
                        0.00006958437006687745,
                        0.0000047704766075185034,
                        0.0000021015366655774415,
                        3.07008640731965e-8,
                    ],
                })]
            ],
        },
    ],
}
