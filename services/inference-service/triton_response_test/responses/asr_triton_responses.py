"""Triton-level stub responses for the ASR service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for an ASR
infer call.  The inference service reads ``outputs[0].data`` as the list of
transcribed text segments.

For audio services the payload size proxy is the length of the base64-encoded
audio string — longer audio → larger base64 → higher bucket.

Three sizes:
  SMALL_ASR_TRITON_RESPONSE   — short utterance, 1 transcript segment
  MEDIUM_ASR_TRITON_RESPONSE  — one or two sentences, 1 segment
  LARGE_ASR_TRITON_RESPONSE   — multi-sentence paragraph, 3 VAD segments
"""

from typing import Any

SMALL_ASR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "whisper",
    "model_version": "1",
    "outputs": [
        {
            "name": "TRANSCRIPTS",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": ["हेलो"],
        }
    ],
}

MEDIUM_ASR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "whisper",
    "model_version": "1",
    "outputs": [
        {
            "name": "TRANSCRIPTS",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": ["नमस्ते, आज मौसम बहुत अच्छा है। कृपया अपना नाम बताइए।"],
        }
    ],
}

LARGE_ASR_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "whisper",
    "model_version": "1",
    "outputs": [
        {
            "name": "TRANSCRIPTS",
            "datatype": "BYTES",
            "shape": [3, 1],
            "data": [
                "कृत्रिम बुद्धिमत्ता आज के समय में बहुत तेज़ी से विकास कर रही है।",
                "इसका उपयोग स्वास्थ्य सेवा, शिक्षा, कृषि और अनेक क्षेत्रों में किया जा रहा है।",
                "प्राकृतिक भाषा प्रसंस्करण के क्षेत्र में विशेष रूप से बड़ी प्रगति हुई है।",
            ],
        }
    ],
}
