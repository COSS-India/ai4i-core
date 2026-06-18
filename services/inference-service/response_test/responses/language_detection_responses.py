"""Pre-defined Language Detection responses for response-size load testing.

Responses verified against the real dev instance.
Each response mirrors the exact output of the language-detection inference endpoint:
  "source"         — original input text
  "langPrediction" — list containing one prediction object with:
      "input"      — echo of the input text (from raw model output)
      "langCode"   — ISO language + script tag (e.g. "eng_Latn", "hin_Deva")
      "confidence" — float in range 0.0–1.0
      "model"      — model name used for prediction (e.g. "IndicLID-FTR")
  "config"         — present but null (smr_response is excluded by the route handler)

Three sizes are provided:
  SMALL_LANGUAGE_DETECTION_RESPONSE   — single short phrase
  MEDIUM_LANGUAGE_DETECTION_RESPONSE  — a few sentences
  LARGE_LANGUAGE_DETECTION_RESPONSE   — full paragraph
"""

from typing import Any

SMALL_LANGUAGE_DETECTION_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": "hello how are you",
            "langPrediction": [
                {
                    "input": "hello how are you",
                    "langCode": "eng_Latn",
                    "confidence": 0.9823415279388428,
                    "model": "IndicLID-FTR",
                }
            ],
        }
    ],
    "config": None,
}

MEDIUM_LANGUAGE_DETECTION_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": (
                "The quick brown fox jumps over the lazy dog. "
                "This sentence contains every letter of the English alphabet at least once. "
                "It is commonly used for testing fonts and keyboards. "
                "The weather today is sunny with clear skies and a gentle breeze."
            ),
            "langPrediction": [
                {
                    "input": (
                        "The quick brown fox jumps over the lazy dog. "
                        "This sentence contains every letter of the English alphabet at least once. "
                        "It is commonly used for testing fonts and keyboards. "
                        "The weather today is sunny with clear skies and a gentle breeze."
                    ),
                    "langCode": "eng_Latn",
                    "confidence": 0.9971204400062561,
                    "model": "IndicLID-FTR",
                }
            ],
        }
    ],
    "config": None,
}

LARGE_LANGUAGE_DETECTION_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": (
                "Language detection is the process of identifying the natural language of a given text. "
                "It is a fundamental step in many natural language processing pipelines. "
                "Modern language detection models can identify hundreds of languages with high accuracy. "
                "The challenge increases when the input text is short or contains mixed languages. "
                "Indic languages present unique challenges because many share similar scripts. "
                "For example, Hindi, Marathi, and Sanskrit all use the Devanagari script. "
                "Bengali and Assamese share a very similar script as well. "
                "Models like IndicLID are specifically trained to distinguish between these closely related languages. "
                "They use both the character n-gram features and the script information together. "
                "In a multilingual country like India, accurate language detection is critical "
                "for routing text to the correct downstream service such as translation or transliteration. "
                "Low-resource languages benefit the most from dedicated detection models "
                "because general-purpose models often confuse them with higher-resource cousins."
            ),
            "langPrediction": [
                {
                    "input": (
                        "Language detection is the process of identifying the natural language of a given text. "
                        "It is a fundamental step in many natural language processing pipelines. "
                        "Modern language detection models can identify hundreds of languages with high accuracy. "
                        "The challenge increases when the input text is short or contains mixed languages. "
                        "Indic languages present unique challenges because many share similar scripts. "
                        "For example, Hindi, Marathi, and Sanskrit all use the Devanagari script. "
                        "Bengali and Assamese share a very similar script as well. "
                        "Models like IndicLID are specifically trained to distinguish between these closely related languages. "
                        "They use both the character n-gram features and the script information together. "
                        "In a multilingual country like India, accurate language detection is critical "
                        "for routing text to the correct downstream service such as translation or transliteration. "
                        "Low-resource languages benefit the most from dedicated detection models "
                        "because general-purpose models often confuse them with higher-resource cousins."
                    ),
                    "langCode": "eng_Latn",
                    "confidence": 0.9994871020317078,
                    "model": "IndicLID-FTR",
                }
            ],
        }
    ],
    "config": None,
}
