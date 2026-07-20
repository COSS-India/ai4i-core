"""Triton-level stub responses for the OCR service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for an OCR
infer call.  Each element in ``outputs[0].data`` is a JSON string with keys
``full_text`` and ``success``.

Payload size proxy is the length of the base64-encoded image string.

Three sizes:
  SMALL_OCR_TRITON_RESPONSE   — single short text extraction
  MEDIUM_OCR_TRITON_RESPONSE  — a sentence or form field block
  LARGE_OCR_TRITON_RESPONSE   — multi-line document extraction (2 images)
"""

import json
from typing import Any

SMALL_OCR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ocr",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                json.dumps({"full_text": "नमस्ते", "success": True})
            ],
        }
    ],
}

MEDIUM_OCR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ocr",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                json.dumps({
                    "full_text": "भारत एक विविधताओं से भरा देश है। यहाँ अनेक भाषाएँ और संस्कृतियाँ एक साथ फलती-फूलती हैं।",
                    "success": True,
                })
            ],
        }
    ],
}

LARGE_OCR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "ocr",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [2, 1],
            "data": [
                json.dumps({
                    "full_text": (
                        "कृत्रिम बुद्धिमत्ता आज के समय में बहुत तेज़ी से विकास कर रही है। "
                        "इसका उपयोग स्वास्थ्य सेवा, शिक्षा, कृषि और अनेक क्षेत्रों में किया जा रहा है। "
                        "भारत में भी कई स्टार्टअप और बड़ी कंपनियाँ इस दिशा में काम कर रही हैं।"
                    ),
                    "success": True,
                }),
                json.dumps({
                    "full_text": (
                        "प्राकृतिक भाषा प्रसंस्करण के क्षेत्र में विशेष रूप से बड़ी प्रगति हुई है। "
                        "वाक् पहचान प्रणालियाँ अब हिंदी और अन्य भारतीय भाषाओं को भी अच्छी तरह समझ सकती हैं।"
                    ),
                    "success": True,
                }),
            ],
        }
    ],
}
