"""Unit tests for LanguageDetectionTaskService — postprocess_output normalizes
langPrediction inner keys to the ULCA contract (langCode/ScriptCode/langScore)."""

import sys
import os
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.asyncio


async def test_normalizes_prediction_keys_from_common_aliases(language_detection_service):
    from services.base.task_service import BaseTaskService, PostProcessFormat

    canned = {"output": [{
        "source": "hello",
        "langPrediction": [{"lang_code": "eng_Latn", "confidence": 0.98, "script": "Latn"}],
    }]}
    with patch.object(BaseTaskService, "postprocess_output", new=AsyncMock(return_value=canned)):
        result = PostProcessFormat(payload={}, response_data=[])
        response = await language_detection_service.postprocess_output(result)

    assert response["output"][0]["langPrediction"] == [
        {"langCode": "eng_Latn", "ScriptCode": "Latn", "langScore": 0.98}
    ]


async def test_preserves_already_ulca_named_keys(language_detection_service):
    from services.base.task_service import BaseTaskService, PostProcessFormat

    canned = {"output": [{
        "source": "hello",
        "langPrediction": [{"langCode": "eng_Latn", "ScriptCode": "Latn", "langScore": 0.98}],
    }]}
    with patch.object(BaseTaskService, "postprocess_output", new=AsyncMock(return_value=canned)):
        result = PostProcessFormat(payload={}, response_data=[])
        response = await language_detection_service.postprocess_output(result)

    assert response["output"][0]["langPrediction"] == [
        {"langCode": "eng_Latn", "ScriptCode": "Latn", "langScore": 0.98}
    ]


async def test_omits_missing_fields_rather_than_inventing_them(language_detection_service):
    from services.base.task_service import BaseTaskService, PostProcessFormat

    canned = {"output": [{"source": "hello", "langPrediction": [{"code": "eng_Latn"}]}]}
    with patch.object(BaseTaskService, "postprocess_output", new=AsyncMock(return_value=canned)):
        result = PostProcessFormat(payload={}, response_data=[])
        response = await language_detection_service.postprocess_output(result)

    assert response["output"][0]["langPrediction"] == [{"langCode": "eng_Latn"}]


async def test_preserves_source_and_leaves_non_list_predictions_untouched(language_detection_service):
    from services.base.task_service import BaseTaskService, PostProcessFormat

    canned = {"output": [{"source": "hello", "langPrediction": None}]}
    with patch.object(BaseTaskService, "postprocess_output", new=AsyncMock(return_value=canned)):
        result = PostProcessFormat(payload={}, response_data=[])
        response = await language_detection_service.postprocess_output(result)

    assert response["output"][0] == {"source": "hello", "langPrediction": None}
