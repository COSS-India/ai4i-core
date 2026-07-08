"""
Triton stub dispatcher for load testing.

When the environment variable TRITON_STUB_MODE is set to "1", "true", or "yes",
_call_triton_inference in BaseTaskService returns a pre-defined stub response
based on the payload size bucket instead of making real HTTP calls to Triton.

Size thresholds (character length of the primary input data):
    SMALL  : < 200 chars
    MEDIUM : 200–999 chars
    LARGE  : ≥ 1000 chars
"""

import copy

from .base_triton_response_test import SMALL_THRESHOLD, MEDIUM_THRESHOLD
from .responses.nmt_triton_responses import (
    SMALL_NMT_TRITON_RESPONSE,
    MEDIUM_NMT_TRITON_RESPONSE,
    LARGE_NMT_TRITON_RESPONSE,
)
from .responses.asr_triton_responses import (
    SMALL_ASR_TRITON_RESPONSE,
    MEDIUM_ASR_TRITON_RESPONSE,
    LARGE_ASR_TRITON_RESPONSE,
)
from .responses.tts_triton_responses import (
    SMALL_TTS_TRITON_RESPONSE,
    MEDIUM_TTS_TRITON_RESPONSE,
    LARGE_TTS_TRITON_RESPONSE,
)
from .responses.ocr_triton_responses import (
    SMALL_OCR_TRITON_RESPONSE,
    MEDIUM_OCR_TRITON_RESPONSE,
    LARGE_OCR_TRITON_RESPONSE,
)
from .responses.ner_triton_responses import (
    SMALL_NER_TRITON_RESPONSE,
    MEDIUM_NER_TRITON_RESPONSE,
    LARGE_NER_TRITON_RESPONSE,
)
from .responses.language_detection_triton_responses import (
    SMALL_LANG_DETECT_TRITON_RESPONSE,
    MEDIUM_LANG_DETECT_TRITON_RESPONSE,
    LARGE_LANG_DETECT_TRITON_RESPONSE,
)
from .responses.audio_lang_detection_triton_responses import (
    SMALL_ALD_TRITON_RESPONSE,
    MEDIUM_ALD_TRITON_RESPONSE,
    LARGE_ALD_TRITON_RESPONSE,
)
from .responses.language_diarization_triton_responses import (
    SMALL_LANG_DIAR_TRITON_RESPONSE,
    MEDIUM_LANG_DIAR_TRITON_RESPONSE,
    LARGE_LANG_DIAR_TRITON_RESPONSE,
)
from .responses.speaker_diarization_triton_responses import (
    SMALL_SD_TRITON_RESPONSE,
    MEDIUM_SD_TRITON_RESPONSE,
    LARGE_SD_TRITON_RESPONSE,
)
from .responses.transliteration_triton_responses import (
    SMALL_TRANSLIT_TRITON_RESPONSE,
    MEDIUM_TRANSLIT_TRITON_RESPONSE,
    LARGE_TRANSLIT_TRITON_RESPONSE,
)
from .responses.llm_responses import (
    SMALL_LLM_RESPONSE,
    MEDIUM_LLM_RESPONSE,
    LARGE_LLM_RESPONSE,
)

# Maps service class name → (small_stub, medium_stub, large_stub)
_STUBS = {
    "NMTTaskService": (
        SMALL_NMT_TRITON_RESPONSE,
        MEDIUM_NMT_TRITON_RESPONSE,
        LARGE_NMT_TRITON_RESPONSE,
    ),
    "ASRTaskService": (
        SMALL_ASR_TRITON_RESPONSE,
        MEDIUM_ASR_TRITON_RESPONSE,
        LARGE_ASR_TRITON_RESPONSE,
    ),
    "TTSTaskService": (
        SMALL_TTS_TRITON_RESPONSE,
        MEDIUM_TTS_TRITON_RESPONSE,
        LARGE_TTS_TRITON_RESPONSE,
    ),
    "OCRTaskService": (
        SMALL_OCR_TRITON_RESPONSE,
        MEDIUM_OCR_TRITON_RESPONSE,
        LARGE_OCR_TRITON_RESPONSE,
    ),
    "NERTaskService": (
        SMALL_NER_TRITON_RESPONSE,
        MEDIUM_NER_TRITON_RESPONSE,
        LARGE_NER_TRITON_RESPONSE,
    ),
    "LanguageDetectionTaskService": (
        SMALL_LANG_DETECT_TRITON_RESPONSE,
        MEDIUM_LANG_DETECT_TRITON_RESPONSE,
        LARGE_LANG_DETECT_TRITON_RESPONSE,
    ),
    "AudioLanguageDetectionTaskService": (
        SMALL_ALD_TRITON_RESPONSE,
        MEDIUM_ALD_TRITON_RESPONSE,
        LARGE_ALD_TRITON_RESPONSE,
    ),
    "LanguageDiarizationTaskService": (
        SMALL_LANG_DIAR_TRITON_RESPONSE,
        MEDIUM_LANG_DIAR_TRITON_RESPONSE,
        LARGE_LANG_DIAR_TRITON_RESPONSE,
    ),
    "SpeakerDiarizationTaskService": (
        SMALL_SD_TRITON_RESPONSE,
        MEDIUM_SD_TRITON_RESPONSE,
        LARGE_SD_TRITON_RESPONSE,
    ),
    "TransliterationTaskService": (
        SMALL_TRANSLIT_TRITON_RESPONSE,
        MEDIUM_TRANSLIT_TRITON_RESPONSE,
        LARGE_TRANSLIT_TRITON_RESPONSE,
    ),
}


def _extract_payload_string(triton_inputs):
    """
    Flatten the data from the first non-empty Triton input tensor into a
    single string whose length is used as the size proxy.

    Works for both text inputs (strings) and audio/image inputs (base64
    strings) — the latter are longer by nature, which gives a proportional
    size signal without special-casing.
    """
    for inp in triton_inputs:
        data = inp.get("data", [])
        if not data:
            continue
        # Numeric arrays (e.g. audio samples) can hold hundreds of thousands
        # of values; size off element count instead of str()-ing each one,
        # which was an O(N) per-request cost that dwarfed the real work.
        if isinstance(data, list) and isinstance(data[0], (int, float)):
            return "0" * len(data)
        parts = []
        stack = list(data)
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif item is not None:
                parts.append(str(item))
        combined = "".join(parts)
        if combined:
            return combined
    return ""


def _binary_payload_len(triton_inputs):
    """Byte length of the first binary tensor ('_raw'), or None if none.

    Binary tensors (ASR audio samples) carry raw bytes, not a data list, so
    their size proxy is the byte count — no stringifying of any elements.
    """
    for inp in triton_inputs:
        raw = inp.get("_raw")
        if raw is not None:
            return len(raw)
    return None


def _classify(length):
    if length < SMALL_THRESHOLD:
        return 0  # SMALL
    if length < MEDIUM_THRESHOLD:
        return 1  # MEDIUM
    return 2      # LARGE


def get_stub_response(task_name, triton_inputs):
    """
    Return a deep copy of the appropriate stub response dict, or None if no
    stub is registered for this service.

    A deep copy is returned so callers cannot mutate the shared stub constants.
    """
    entry = _STUBS.get(task_name)
    if entry is None:
        return None
    raw_len = _binary_payload_len(triton_inputs)
    length = raw_len if raw_len is not None else len(_extract_payload_string(triton_inputs))
    return copy.deepcopy(entry[_classify(length)])


# Size-bucketed OpenAI chat-completion stubs for the LLM proxy path. Kept
# separate from _STUBS because the LLM body is OpenAI-shaped, not Triton-shaped.
_LLM_STUBS = (SMALL_LLM_RESPONSE, MEDIUM_LLM_RESPONSE, LARGE_LLM_RESPONSE)


def _extract_chat_prompt(payload):
    """Concatenate the string content of an OpenAI chat payload's messages,
    the size proxy for classifying the LLM stub. Non-string content (multimodal
    parts) is ignored for sizing."""
    if not isinstance(payload, dict):
        return ""
    parts = []
    for message in payload.get("messages") or []:
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
    return "".join(parts)


def get_llm_stub_response(payload):
    """
    Return a deep copy of the size-matched OpenAI chat-completion stub for the
    LLM proxy path. Mirrors get_stub_response so the LLM path is stubbed like
    every other service during load testing.
    """
    idx = _classify(len(_extract_chat_prompt(payload)))
    return copy.deepcopy(_LLM_STUBS[idx])
