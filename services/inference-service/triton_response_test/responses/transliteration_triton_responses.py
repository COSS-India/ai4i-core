"""Triton-level stub responses for the Transliteration service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for a
transliteration infer call.  ``outputs[0].data`` holds one or more candidate
transliterations (numSuggestions controls how many).

Three sizes based on input text character length:
  SMALL_TRANSLIT_TRITON_RESPONSE   — single short word/phrase  (< 200 chars)
  MEDIUM_TRANSLIT_TRITON_RESPONSE  — a short sentence          (200–999 chars)
  LARGE_TRANSLIT_TRITON_RESPONSE   — a multi-word passage      (>= 1000 chars)
"""

from typing import Any

SMALL_TRANSLIT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "transliteration",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 3],
            "data": ["नमस्ते", "नमस्तें", "नमस्तए"],
        }
    ],
}

MEDIUM_TRANSLIT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "transliteration",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 3],
            "data": [
                "आर्टिफिशियल इंटेलिजेंस आज के युग में बहुत महत्वपूर्ण है।",
                "आर्टिफ़िशियल इंटेलिजेंस आज के युग में बहुत महत्वपूर्ण है।",
                "आर्टिफिशल इन्टेलिजेन्स आज के युग में बहुत महत्वपूर्ण है।",
            ],
        }
    ],
}

LARGE_TRANSLIT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "transliteration",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 3],
            "data": [
                "आर्टिफिशियल इंटेलिजेंस हमारे दैनिक जीवन में टेक्नोलॉजी के साथ हमारी इंटरेक्शन के तरीके को ट्रांसफॉर्म कर रही है। हेल्थकेयर से एजुकेशन तक, AI-पावर्ड सिस्टम्स प्रोफेशनल्स को फास्टर और मोर एक्यूरेट डिसीजन लेने में हेल्प कर रहे हैं।",
                "आर्टिफ़िशियल इंटेलिजेंस हमारे डेली लाइफ में टेक्नोलॉजी के साथ हमारी इंटरेक्शन के तरीके को ट्रांसफॉर्म कर रही है। हेल्थकेयर से एजुकेशन तक, AI-पावर्ड सिस्टम्स प्रोफेशनल्स को फास्टर और मोर एक्यूरेट डिसीजन लेने में हेल्प कर रहे हैं।",
                "आर्टिफिशल इन्टेलिजेन्स हमारे दैनिक जीवन में टेक्नोलॉजी के साथ हमारी इन्टरेक्शन के तरीके को ट्रान्सफॉर्म कर रही है। हेल्थकेयर से एजुकेशन तक, AI-पावर्ड सिस्टम्स प्रोफेशनल्स को फास्टर और मोर एक्यूरेट डिसीजन लेने में हेल्प कर रहे हैं।",
            ],
        }
    ],
}
