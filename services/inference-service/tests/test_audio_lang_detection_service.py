"""Unit tests for AudioLanguageDetectionTaskService — postprocess_output
reshapes the adapter-mapped flat fields into ULCA's langPrediction list."""

import sys
import os
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.asyncio


async def test_builds_lang_prediction_from_all_scores(audio_lang_detection_service):
    from services.base.task_service import BaseTaskService, PostProcessFormat

    canned = {
        "taskType": "audio-lang-detection",
        "output": [{
            "language_code": "hin_Deva",
            "confidence": 0.94,
            "all_scores": {"hin_Deva": 0.94, "eng_Latn": 0.04},
        }],
        "config": {"serviceId": "svc-1"},
    }
    with patch.object(BaseTaskService, "postprocess_output", new=AsyncMock(return_value=canned)):
        result = PostProcessFormat(payload={}, response_data=[])
        response = await audio_lang_detection_service.postprocess_output(result)

    assert response["taskType"] == "audio-lang-detection"
    assert response["config"] == {"serviceId": "svc-1"}
    assert response["output"] == [{"langPrediction": [
        {"langCode": "hin_Deva", "langScore": 0.94},
        {"langCode": "eng_Latn", "langScore": 0.04},
    ]}]


async def test_falls_back_to_language_code_and_confidence_when_all_scores_missing(audio_lang_detection_service):
    from services.base.task_service import BaseTaskService, PostProcessFormat

    canned = {"output": [{"language_code": "hin_Deva", "confidence": 0.94, "all_scores": None}]}
    with patch.object(BaseTaskService, "postprocess_output", new=AsyncMock(return_value=canned)):
        result = PostProcessFormat(payload={}, response_data=[])
        response = await audio_lang_detection_service.postprocess_output(result)

    assert response["output"] == [{"langPrediction": [{"langCode": "hin_Deva", "langScore": 0.94}]}]


async def test_falls_back_when_all_scores_is_not_a_dict(audio_lang_detection_service):
    from services.base.task_service import BaseTaskService, PostProcessFormat

    canned = {"output": [{"language_code": "hin_Deva", "confidence": 0.94, "all_scores": ["not", "a", "dict"]}]}
    with patch.object(BaseTaskService, "postprocess_output", new=AsyncMock(return_value=canned)):
        result = PostProcessFormat(payload={}, response_data=[])
        response = await audio_lang_detection_service.postprocess_output(result)

    assert response["output"] == [{"langPrediction": [{"langCode": "hin_Deva", "langScore": 0.94}]}]


async def test_empty_prediction_when_no_language_code_available(audio_lang_detection_service):
    from services.base.task_service import BaseTaskService, PostProcessFormat

    canned = {"output": [{}]}
    with patch.object(BaseTaskService, "postprocess_output", new=AsyncMock(return_value=canned)):
        result = PostProcessFormat(payload={}, response_data=[])
        response = await audio_lang_detection_service.postprocess_output(result)

    assert response["output"] == [{"langPrediction": []}]
