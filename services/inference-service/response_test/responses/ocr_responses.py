"""Pre-defined OCR responses for response-size load testing.

Responses verified against the real dev instance output contract.
Each response mirrors the exact output of the OCR inference endpoint:
  "output"       — list with one item containing:
      "source"   — JSON *string* (stringified) containing:
          "success"     — bool, always true on successful extraction
          "text_lines"  — list of objects, each with:
              "text"        — string, recognised text for the line
              "confidence"  — float 0.0–1.0
              "bbox"        — [x1, y1, x2, y2] bounding box (4 floats)
              "polygon"     — [[x,y], [x,y], [x,y], [x,y]] (4 corner points)
          "full_text"   — newline-joined concatenation of all text_lines texts
          "image_bbox"  — [0.0, 0.0, width, height] of the source image
      "target"   — always ""
  "config"       — populated with serviceId, language (sourceLanguage +
                   sourceScriptCode), and textDetection flag
  "smr_response" — always null (present, unlike diarization services)

Key structural quirk: output[0]["source"] is a JSON *string*, not a dict —
callers must json.loads() it to access text_lines and full_text.

Three sizes are provided:
  SMALL_OCR_RESPONSE   — image with 3 text lines
  MEDIUM_OCR_RESPONSE  — image with 7 text lines
  LARGE_OCR_RESPONSE   — image with 12 text lines (from real dev response)
"""

import json
from typing import Any

_SERVICE_ID = "14e4a9fb949aa86af0b88a5a1879558d"

_SMALL_SOURCE: dict[str, Any] = {
    "success": True,
    "text_lines": [
        {
            "text": "Hello World",
            "confidence": 0.9984256029129028,
            "bbox": [10.0, 10.0, 150.0, 22.0],
            "polygon": [[10.0, 10.0], [150.0, 10.0], [150.0, 22.0], [10.0, 22.0]],
        },
        {
            "text": "This is a test image.",
            "confidence": 0.9991432189941406,
            "bbox": [10.0, 28.0, 180.0, 40.0],
            "polygon": [[10.0, 28.0], [180.0, 28.0], [180.0, 40.0], [10.0, 40.0]],
        },
        {
            "text": "Simple OCR text here.",
            "confidence": 0.9978543281555176,
            "bbox": [10.0, 46.0, 178.0, 58.0],
            "polygon": [[10.0, 46.0], [178.0, 46.0], [178.0, 58.0], [10.0, 58.0]],
        },
    ],
    "full_text": "Hello World\nThis is a test image.\nSimple OCR text here.",
    "image_bbox": [0.0, 0.0, 200.0, 70.0],
}

_MEDIUM_SOURCE: dict[str, Any] = {
    "success": True,
    "text_lines": [
        {
            "text": "The quick brown fox jumps",
            "confidence": 0.9993145465850830,
            "bbox": [10.0, 10.0, 220.0, 22.0],
            "polygon": [[10.0, 10.0], [220.0, 10.0], [220.0, 22.0], [10.0, 22.0]],
        },
        {
            "text": "over the lazy dog. Pack my",
            "confidence": 0.9996801614761353,
            "bbox": [10.0, 26.0, 222.0, 38.0],
            "polygon": [[10.0, 26.0], [222.0, 26.0], [222.0, 38.0], [10.0, 38.0]],
        },
        {
            "text": "box with five dozen liquor",
            "confidence": 0.9995231628417969,
            "bbox": [10.0, 42.0, 221.0, 54.0],
            "polygon": [[10.0, 42.0], [221.0, 42.0], [221.0, 54.0], [10.0, 54.0]],
        },
        {
            "text": "jugs. How vexingly quick",
            "confidence": 0.9988765716552734,
            "bbox": [10.0, 58.0, 219.0, 70.0],
            "polygon": [[10.0, 58.0], [219.0, 58.0], [219.0, 70.0], [10.0, 70.0]],
        },
        {
            "text": "daft zebras jump! Bright",
            "confidence": 0.9992341995239258,
            "bbox": [10.0, 74.0, 218.0, 86.0],
            "polygon": [[10.0, 74.0], [218.0, 74.0], [218.0, 86.0], [10.0, 86.0]],
        },
        {
            "text": "vixens jump; dozy fowl",
            "confidence": 0.9987654209136963,
            "bbox": [10.0, 90.0, 217.0, 102.0],
            "polygon": [[10.0, 90.0], [217.0, 90.0], [217.0, 102.0], [10.0, 102.0]],
        },
        {
            "text": "quack. Sphinx of black quartz.",
            "confidence": 0.9994123077392578,
            "bbox": [10.0, 106.0, 230.0, 118.0],
            "polygon": [[10.0, 106.0], [230.0, 106.0], [230.0, 118.0], [10.0, 118.0]],
        },
    ],
    "full_text": (
        "The quick brown fox jumps\n"
        "over the lazy dog. Pack my\n"
        "box with five dozen liquor\n"
        "jugs. How vexingly quick\n"
        "daft zebras jump! Bright\n"
        "vixens jump; dozy fowl\n"
        "quack. Sphinx of black quartz."
    ),
    "image_bbox": [0.0, 0.0, 241.0, 130.0],
}

# LARGE source uses the exact text from the real dev instance response.
_LARGE_SOURCE: dict[str, Any] = {
    "success": True,
    "text_lines": [
        {
            "text": "Cedric himself knew nothing",
            "confidence": 0.998443905649514,
            "bbox": [24.0, 11.0, 229.0, 24.0],
            "polygon": [[24.0, 11.0], [229.0, 12.0], [229.0, 24.0], [24.0, 22.0]],
        },
        {
            "text": "whatever about it. It had never been",
            "confidence": 0.9996901091776396,
            "bbox": [10.0, 27.0, 228.0, 38.0],
            "polygon": [[10.0, 28.0], [228.0, 27.0], [228.0, 38.0], [10.0, 38.0]],
        },
        {
            "text": "even mentioned to him. He knew that",
            "confidence": 0.9998533226348258,
            "bbox": [10.0, 43.0, 230.0, 54.0],
            "polygon": [[10.0, 43.0], [230.0, 44.0], [230.0, 54.0], [10.0, 53.0]],
        },
        {
            "text": "his papa had been an Englishman,",
            "confidence": 0.9996176975614884,
            "bbox": [10.0, 59.0, 229.0, 71.0],
            "polygon": [[10.0, 59.0], [229.0, 59.0], [229.0, 71.0], [10.0, 71.0]],
        },
        {
            "text": "because his mamma had told him so:",
            "confidence": 0.9996901965803571,
            "bbox": [11.0, 75.0, 229.0, 86.0],
            "polygon": [[11.0, 75.0], [229.0, 75.0], [229.0, 86.0], [11.0, 86.0]],
        },
        {
            "text": "but then his papa had died when he",
            "confidence": 0.99977874259154,
            "bbox": [10.0, 91.0, 230.0, 103.0],
            "polygon": [[10.0, 91.0], [230.0, 91.0], [230.0, 103.0], [10.0, 103.0]],
        },
        {
            "text": "was so little a boy that he could not",
            "confidence": 0.9999130414082453,
            "bbox": [10.0, 106.0, 230.0, 119.0],
            "polygon": [[10.0, 106.0], [230.0, 106.0], [230.0, 119.0], [10.0, 119.0]],
        },
        {
            "text": "remember very much about him.",
            "confidence": 0.9993981372925543,
            "bbox": [10.0, 122.0, 229.0, 134.0],
            "polygon": [[10.0, 122.0], [229.0, 122.0], [229.0, 134.0], [10.0, 134.0]],
        },
        {
            "text": "except that he was big, and had blue",
            "confidence": 0.9997626652843074,
            "bbox": [10.0, 138.0, 229.0, 150.0],
            "polygon": [[10.0, 138.0], [229.0, 138.0], [229.0, 150.0], [10.0, 150.0]],
        },
        {
            "text": "eyes and a long mustache, and that it",
            "confidence": 0.999843955039978,
            "bbox": [10.0, 154.0, 230.0, 166.0],
            "polygon": [[10.0, 154.0], [230.0, 154.0], [230.0, 166.0], [10.0, 166.0]],
        },
        {
            "text": "was a splendid thing to be carried",
            "confidence": 0.9997117304139667,
            "bbox": [10.0, 170.0, 229.0, 182.0],
            "polygon": [[10.0, 170.0], [229.0, 170.0], [229.0, 182.0], [10.0, 182.0]],
        },
        {
            "text": "around the room on his shoulder.",
            "confidence": 0.9997178491424111,
            "bbox": [10.0, 186.0, 229.0, 197.0],
            "polygon": [[10.0, 186.0], [229.0, 186.0], [229.0, 197.0], [10.0, 197.0]],
        },
    ],
    "full_text": (
        "Cedric himself knew nothing\n"
        "whatever about it. It had never been\n"
        "even mentioned to him. He knew that\n"
        "his papa had been an Englishman,\n"
        "because his mamma had told him so:\n"
        "but then his papa had died when he\n"
        "was so little a boy that he could not\n"
        "remember very much about him.\n"
        "except that he was big, and had blue\n"
        "eyes and a long mustache, and that it\n"
        "was a splendid thing to be carried\n"
        "around the room on his shoulder."
    ),
    "image_bbox": [0.0, 0.0, 241.0, 209.0],
}

_CONFIG: dict[str, Any] = {
    "serviceId": _SERVICE_ID,
    "language": {
        "sourceLanguage": "en",
        "sourceScriptCode": "",
    },
    "textDetection": True,
}

SMALL_OCR_RESPONSE: dict[str, Any] = {
    "output": [{"source": json.dumps(_SMALL_SOURCE), "target": ""}],
    "config": _CONFIG,
    "smr_response": None,
}

MEDIUM_OCR_RESPONSE: dict[str, Any] = {
    "output": [{"source": json.dumps(_MEDIUM_SOURCE), "target": ""}],
    "config": _CONFIG,
    "smr_response": None,
}

LARGE_OCR_RESPONSE: dict[str, Any] = {
    "output": [{"source": json.dumps(_LARGE_SOURCE), "target": ""}],
    "config": _CONFIG,
    "smr_response": None,
}
