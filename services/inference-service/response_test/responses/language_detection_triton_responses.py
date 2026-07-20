"""Triton-level stub responses for the Language Detection service (IndicLID).

IndicLID returns a single OUTPUT_TEXT tensor whose data element is a JSON
string.  The inference service adapter_config applies json_parse + wrap_list
to produce langPrediction.

Three sizes based on input text character length:
  SMALL_LANG_DETECT_TRITON_RESPONSE   — short phrase   (< 200 chars)
  MEDIUM_LANG_DETECT_TRITON_RESPONSE  — a few sentences (200–999 chars)
  LARGE_LANG_DETECT_TRITON_RESPONSE   — full paragraph  (>= 1000 chars)
"""

import json
from typing import Any


def _pred(lang_code, lang_name, confidence):
    return json.dumps({
        "langCode": lang_code,
        "langName": lang_name,
        "confidence": confidence,
    })


SMALL_LANG_DETECT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "indiclid",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [_pred("en", "English", 0.9823)],
        }
    ],
}

MEDIUM_LANG_DETECT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "indiclid",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [_pred("en", "English", 0.9971)],
        }
    ],
}

LARGE_LANG_DETECT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "indiclid",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [_pred("en", "English", 0.9995)],
        }
    ],
}
