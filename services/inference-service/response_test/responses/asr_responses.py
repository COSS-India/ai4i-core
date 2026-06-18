"""Pre-defined ASR responses for response-size load testing.

Responses verified against the real dev instance output contract.
Each response mirrors the exact output of the ASR inference endpoint:
  "source"       — transcribed text produced by the model
  "nBestTokens"  — always null (alternative token sequences not returned)
  "config"       — always null
  "smr_response" — always null

Unlike text services, the ASR endpoint does NOT use response_model_exclude,
so all three envelope fields (config, smr_response, and nBestTokens) are
present in every response.

Three sizes are provided, corresponding to short / medium / long audio clips:
  SMALL_ASR_RESPONSE   — short utterance (a few words)
  MEDIUM_ASR_RESPONSE  — a sentence or two
  LARGE_ASR_RESPONSE   — a multi-sentence paragraph
"""

from typing import Any

SMALL_ASR_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": "हेलो",
            "nBestTokens": None,
        }
    ],
    "config": None,
    "smr_response": None,
}

MEDIUM_ASR_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": "नमस्ते, आज मौसम बहुत अच्छा है। कृपया अपना नाम बताइए।",
            "nBestTokens": None,
        }
    ],
    "config": None,
    "smr_response": None,
}

LARGE_ASR_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": (
                "कृत्रिम बुद्धिमत्ता आज के समय में बहुत तेज़ी से विकास कर रही है। "
                "इसका उपयोग स्वास्थ्य सेवा, शिक्षा, कृषि और अनेक क्षेत्रों में किया जा रहा है। "
                "भारत में भी कई स्टार्टअप और बड़ी कंपनियाँ इस दिशा में काम कर रही हैं। "
                "प्राकृतिक भाषा प्रसंस्करण के क्षेत्र में विशेष रूप से बड़ी प्रगति हुई है। "
                "वाक् पहचान प्रणालियाँ अब हिंदी और अन्य भारतीय भाषाओं को भी अच्छी तरह समझ सकती हैं।"
            ),
            "nBestTokens": None,
        }
    ],
    "config": None,
    "smr_response": None,
}
