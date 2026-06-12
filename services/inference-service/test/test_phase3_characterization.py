"""Characterization tests for the v2 migration-target services (AI4IDS-1981 Phase 3).

Pins the current v1 task-type output (golden master) for OCR, Transliteration,
Language Detection, Audio Language Detection, and Language Diarization, so the
Phase 4 migration to JSONata configs can be proven byte-for-byte identical.
Only the Triton HTTP is mocked; the real v1 adapter_config drives the output.

(TTS, ASR, Speaker Diarization, NMT are pinned by test_phase4_characterization
and the NMT e2e suite. NER and TTS keep code-side output and do not migrate.)
"""

import base64
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, ".")

_B64 = base64.b64encode(b"fake").decode()


async def _run(service, payload, triton_response):
    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=triton_response),
    ):
        return await service.process(payload)


# ── OCR ────────────────────────────────────────────────────────────────────────

async def test_ocr_v1_output():
    from services.ocr_service import OCRTaskService

    service = OCRTaskService(service_info={
        "name": "surya-ocr", "endpoint": "http://triton/m/infer", "api_key": None,
        "adapter_config": {
            "version": "1", "model_version": "1",
            "inputs": [{"tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1],
                        "value_path": "input.image_content"}],
            "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "text",
                         "response_key": "output[].source"}],
            "response": {"static_item_fields": {"target": ""}},
        },
    })
    out = await _run(
        service,
        {"image": [{"imageContent": _B64, "imageFormat": "png"}],
         "config": {"language": {"sourceLanguage": "en"}}},
        {"outputs": [{"name": "OUTPUT_TEXT", "data": ["Hello World"]}]},
    )
    assert out == {
        "output": [{"source": "Hello World", "target": ""}],
        "config": {"language": {"sourceLanguage": "en"}},
    }


# ── Transliteration ─────────────────────────────────────────────────────────────

async def test_transliteration_v1_output():
    from services.transliteration_service import TransliterationTaskService

    service = TransliterationTaskService(service_info={
        "name": "translit", "endpoint": "http://triton/m/infer", "api_key": None,
        "adapter_config": {
            "version": "1.0", "model_version": "1",
            "inputs": [
                {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1], "value_path": "input.source"},
                {"tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1],
                 "value_path": "request.config.language.sourceLanguage"},
                {"tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1],
                 "value_path": "request.config.language.targetLanguage"},
                {"tensor": "IS_WORD_LEVEL", "dtype": "BOOL", "shape": [-1],
                 "value_path": "request.config.is_word_level"},
                {"tensor": "TOP_K", "dtype": "UINT8", "shape": [-1], "value_path": "request.config.top_k"},
            ],
            "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target",
                         "pair_with_input": "input.source"}],
            "response": {"include_config": False},
        },
    })
    out = await _run(
        service,
        {"input": [{"source": "namaste"}],
         "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "en"},
                    "numSuggestions": 0, "isSentence": False}},
        {"outputs": [{"name": "OUTPUT_TEXT", "data": ["नमस्ते"]}]},
    )
    assert out == {"output": [{"source": "namaste", "target": "नमस्ते"}]}


# ── Language Detection ──────────────────────────────────────────────────────────

async def test_language_detection_v1_output():
    from services.language_detection_service import LanguageDetectionTaskService

    service = LanguageDetectionTaskService(service_info={
        "name": "langdetect", "endpoint": "http://triton/m/infer", "api_key": None,
        "adapter_config": {
            "version": "1.0", "model_version": "1",
            "inputs": [{"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1],
                        "value_path": "input.source"}],
            "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "langPrediction",
                         "transform": ["json_parse", "wrap_list"], "pair_with_input": "input.source"}],
            "response": {"include_config": False},
        },
    })
    out = await _run(
        service,
        {"input": [{"source": "hello world"}], "config": {"language": {"sourceLanguage": "hi"}}},
        {"outputs": [{"name": "OUTPUT_TEXT", "data": ['{"langCode":"en","score":0.99}']}]},
    )
    assert out == {
        "output": [{"source": "hello world", "langPrediction": [{"langCode": "en", "score": 0.99}]}]
    }


# ── Audio Language Detection ────────────────────────────────────────────────────

async def test_audio_lang_detection_v1_output():
    from services.audio_lang_detection_service import AudioLanguageDetectionTaskService

    service = AudioLanguageDetectionTaskService(service_info={
        "name": "ald", "endpoint": "http://triton/m/infer", "api_key": None,
        "adapter_config": {
            "version": "1.0", "model_version": "1",
            "inputs": [{"tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1],
                        "value_path": "audio.audio_content"}],
            "outputs": [
                {"tensor": "LANGUAGE_CODE", "dtype": "BYTES", "maps_to": "language_code"},
                {"tensor": "CONFIDENCE", "dtype": "FP32", "maps_to": "confidence"},
                {"tensor": "ALL_SCORES", "dtype": "BYTES", "maps_to": "all_scores", "transform": "json_parse"},
            ],
            "response": {"task_type": "audio-lang-detection", "config_keys": ["serviceId"]},
        },
    })
    out = await _run(
        service,
        {"audio": [{"audioContent": _B64}], "config": {"serviceId": "ald-1"}},
        {"outputs": [{"name": "LANGUAGE_CODE", "data": ["en"]},
                     {"name": "CONFIDENCE", "data": [0.98]},
                     {"name": "ALL_SCORES", "data": ['{"en":0.98,"hi":0.02}']}]},
    )
    assert out == {
        "taskType": "audio-lang-detection",
        "output": [{"language_code": "en", "confidence": 0.98,
                    "all_scores": {"en": 0.98, "hi": 0.02}}],
        "config": {"serviceId": "ald-1"},
    }


# ── Language Diarization ────────────────────────────────────────────────────────

async def test_language_diarization_v1_output():
    from services.language_diarization_service import LanguageDiarizationTaskService

    service = LanguageDiarizationTaskService(service_info={
        "name": "ld", "endpoint": "http://triton/m/infer", "api_key": None,
        "adapter_config": {
            "version": "1.0", "model_version": "1",
            "inputs": [
                {"tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "audio.audio_content"},
                {"tensor": "LANGUAGE", "dtype": "BYTES", "shape": [1, 1], "value_path": "request.config.target_language"},
            ],
            "outputs": [{"tensor": "DIARIZATION_RESULT", "dtype": "BYTES", "maps_to": "diarization_json",
                         "transform": "json_parse", "response_key": "output[]"}],
            "response": {"task_type": "language-diarization", "config_keys": ["serviceId"]},
        },
    })
    out = await _run(
        service,
        {"audio": [{"audioContent": _B64}], "config": {"serviceId": "ld-1"}},
        {"outputs": [{"name": "DIARIZATION_RESULT",
                      "data": ['{"total_segments":1,"segments":[{"start":0.0,"end":1.0,"language":"en"}]}']}]},
    )
    assert out == {
        "taskType": "language-diarization",
        "output": [{"total_segments": 1, "segments": [{"start": 0.0, "end": 1.0, "language": "en"}]}],
        "config": {"serviceId": "ld-1"},
    }
