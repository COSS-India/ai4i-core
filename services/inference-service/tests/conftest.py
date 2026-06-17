"""Shared pytest fixtures for inference-service unit tests."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


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
