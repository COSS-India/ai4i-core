"""
Triton and LLM stub dispatcher for load testing.

Gated on settings.TRITON_STUB_MODE. When it is off both entry points return
None and every caller falls through to the real upstream, which is why the
gate lives here rather than at the two call sites: one switch, no duplicated
condition, and the call sites read as a plain "stub or nothing" lookup.

When it is on, BaseTaskService._call_triton_inference and
OpenAIProxyService.proxy_traced return a canned response picked by payload
size instead of calling Triton or the LLM upstream.

Size thresholds (character length of the primary input data):
    SMALL  : < 200 chars
    MEDIUM : 200-999 chars
    LARGE  : >= 1000 chars
"""

import copy

from config import settings

from .base_response_test import SMALL_THRESHOLD, MEDIUM_THRESHOLD
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
from .responses.audio_transcription_responses import (
    SMALL_AUDIO_BYTES,
    MEDIUM_AUDIO_BYTES,
    SMALL_TRANSCRIPTION_RESPONSES,
    MEDIUM_TRANSCRIPTION_RESPONSES,
    LARGE_TRANSCRIPTION_RESPONSES,
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
    Return a deep copy of the appropriate stub response dict, or None when stub
    mode is off or no stub is registered for this service.

    A deep copy is returned so callers cannot mutate the shared stub constants.
    """
    if not settings.TRITON_STUB_MODE:
        return None
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
    LLM proxy path, or None when stub mode is off. Mirrors get_stub_response so
    the LLM path is stubbed like every other service during load testing.
    """
    if not settings.TRITON_STUB_MODE:
        return None
    idx = _classify(len(_extract_chat_prompt(payload)))
    body = copy.deepcopy(_LLM_STUBS[idx])
    # Echo back the model we were handed, the way vLLM does. By the time
    # forward() runs, proxy_traced has already replaced the client's service ID
    # with the real upstream model name from adapter_config, and the caller
    # reads body["model"] straight onto the model span and the Prometheus
    # label. Returning the fixture's literal "stub" would mislabel both.
    if isinstance(payload, dict) and payload.get("model"):
        body["model"] = payload["model"]
    return body


# Size-bucketed OpenAI speech-to-text stubs for the /audio/* multipart routes.
# Separate from _LLM_STUBS because the body is a transcription, not a chat
# completion, and its shape depends on the response_format form field.
_AUDIO_STUBS = (
    SMALL_TRANSCRIPTION_RESPONSES,
    MEDIUM_TRANSCRIPTION_RESPONSES,
    LARGE_TRANSCRIPTION_RESPONSES,
)

# Formats the /audio/* routes advertise. Anything else falls back to json,
# matching the route default rather than returning a shape the caller cannot
# interpret.
_DEFAULT_AUDIO_FORMAT = "json"


def _upload_byte_len(files):
    """Byte length of the uploaded file in an httpx `files` dict.

    Values are (filename, bytes, content_type) tuples; the raw bytes are the
    only meaningful size proxy for audio.
    """
    for value in (files or {}).values():
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            payload = value[1]
            if isinstance(payload, (bytes, bytearray)):
                return len(payload)
    return 0


def _classify_audio(byte_len):
    if byte_len < SMALL_AUDIO_BYTES:
        return 0  # SMALL
    if byte_len < MEDIUM_AUDIO_BYTES:
        return 1  # MEDIUM
    return 2      # LARGE


def get_audio_stub_response(files, data):
    """
    Return a deep copy of the size-matched speech-to-text stub for the
    /audio/* multipart path, or None when stub mode is off.

    The body type follows the response_format form field: a dict for json /
    verbose_json, a str for text / srt / vtt. _proxy_audio_upload picks
    JSONResponse vs PlainTextResponse off that type, so returning the wrong
    one would change the response content type.
    """
    if not settings.TRITON_STUB_MODE:
        return None
    bucket = _AUDIO_STUBS[_classify_audio(_upload_byte_len(files))]
    response_format = str((data or {}).get("response_format") or _DEFAULT_AUDIO_FORMAT).lower()
    body = bucket.get(response_format, bucket[_DEFAULT_AUDIO_FORMAT])
    return copy.deepcopy(body)
