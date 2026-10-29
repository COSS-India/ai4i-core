"""Shared pytest fixtures for inference-service unit tests."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture(autouse=True)
def _no_service_access_redis(monkeypatch):
    """Keep resolver tests off a real Redis: no core:service:{id}:access key,
    so the resolved flags are whatever the test's MMS response says.
    test_service_access.py patches this per test."""
    async def _missing(service_id):
        return None

    resolver_module = sys.modules.get("inference.inference_server_resolver")
    if resolver_module is not None:
        monkeypatch.setattr(resolver_module, "_read_service_access", _missing, raising=False)


@pytest.fixture
def asr_service():
    from services.asr_service import ASRTaskService
    return ASRTaskService(service_info={
        "name": "whisper", "endpoint": "http://triton:8000",
        "api_key": None, "adapter_config": {},
    })


@pytest.fixture
def tts_service():
    from services.tts_service import TTSTaskService
    return TTSTaskService(service_info={
        "name": "tts-model", "endpoint": "http://triton:8000",
        "api_key": None, "adapter_config": {},
    })


@pytest.fixture
def ner_service():
    from services.ner_service import NERTaskService
    return NERTaskService(service_info={
        "name": "ner-model", "endpoint": "http://triton:8000",
        "api_key": None, "adapter_config": {},
    })


@pytest.fixture
def transliteration_service():
    from services.transliteration_service import TransliterationTaskService
    return TransliterationTaskService(service_info={
        "name": "translit-model", "endpoint": "http://triton:8000",
        "api_key": None, "adapter_config": {},
    })


@pytest.fixture
def speaker_diarization_service():
    from services.speaker_diarization_service import SpeakerDiarizationTaskService
    return SpeakerDiarizationTaskService(service_info={
        "name": "sd-model", "endpoint": "http://triton:8000",
        "api_key": None, "adapter_config": {},
    })


@pytest.fixture
def llm_service():
    from services.llm_service import OpenAIProxyService
    return OpenAIProxyService()
