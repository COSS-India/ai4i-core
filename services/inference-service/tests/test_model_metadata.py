"""
Unit tests for the model-metadata enrichment (AI4IDS feedback-API groundwork):
  1. InferenceServerResolver._normalize_mms_response extracts modelProvider/
     modelVersion/modelId/language from the nested `model` block.
  2. BaseTaskService.process() attaches a `model` block to every task-service
     response, built from that resolved service_info.
"""

from unittest.mock import AsyncMock

from inference.inference_server_resolver import InferenceServerResolver
from services.base.task_service import BaseTaskService, PostProcessFormat


MOCK_MMS_RESPONSE = {
    "success": True,
    "data": {
        "serviceName": "agrinet-model",
        "endpoint": "http://3.109.103.63:8080",
        "apiKey": None,
        "isPublished": True,
        "tierIds": [],
        "model": {
            "modelId": "ade00312aa6b12da51485a25bdf383b6",
            "version": "1.0",
            "classInstance": "TextDefaultModel",
            "submitter": {"name": "IndicTrans"},
            "languages": [{"sourceLanguage": "en", "targetLanguage": "hi"}],
            "inferenceEndPoint": {
                "schema": {"model_name": "agrinet-model"},
                "adapter_config": {"outputs": []},
            },
        },
    },
}


async def test_normalize_mms_response_extracts_model_metadata():
    resolver = InferenceServerResolver()
    resolver._query_model_management_service = AsyncMock(return_value=None)  # unused directly
    normalized = resolver._normalize_mms_response(MOCK_MMS_RESPONSE, "svc-1")

    assert normalized["model_id"] == "ade00312aa6b12da51485a25bdf383b6"
    assert normalized["model_version"] == "1.0"
    assert normalized["model_provider"] == "IndicTrans"
    assert normalized["language"] == [{"sourceLanguage": "en", "targetLanguage": "hi"}]


async def test_normalize_mms_response_defaults_when_submitter_missing():
    raw = {
        "success": True,
        "data": {
            "serviceName": "svc",
            "endpoint": "http://x",
            "model": {"modelId": "abc", "version": "2.0"},
        },
    }
    resolver = InferenceServerResolver()
    normalized = resolver._normalize_mms_response(raw, "svc-1")

    assert normalized["model_provider"] is None
    assert normalized["language"] == []


async def test_process_attaches_model_metadata_block():
    """process() must attach modelProvider/modelVersion/modelId/language,
    resolved from service_info, onto whatever postprocess_output returns."""
    service_info = {
        "name": "agrinet-model",
        "endpoint": "http://triton:8000/v2/models/agrinet-model/infer",
        "api_key": None,
        "adapter_config": None,
        "model_id": "ade00312aa6b12da51485a25bdf383b6",
        "model_version": "1.0",
        "model_provider": "IndicTrans",
        "language": [{"sourceLanguage": "en", "targetLanguage": "hi"}],
    }
    service = BaseTaskService(service_info=service_info)
    service.payload_key = "input"

    async def _fake_run_inference(payload, serviceInfo):
        return PostProcessFormat(
            payload=payload,
            response_data=[{"target": "hi"}],
            source_texts=["hello"],
        )

    service.run_inference = _fake_run_inference
    service._adapter_config = None

    payload = {"input": [{"source": "hello"}], "config": {}}
    response = await service.process(payload, service_info)

    assert response["model"] == {
        "modelProvider": "IndicTrans",
        "modelVersion": "1.0",
        "modelId": "ade00312aa6b12da51485a25bdf383b6",
        "language": [{"sourceLanguage": "en", "targetLanguage": "hi"}],
    }


async def test_process_model_metadata_defaults_when_service_info_lacks_fields():
    """Older/legacy service_info without the new keys must not raise —
    model block degrades to all-None/empty rather than KeyError."""
    service_info = {
        "name": "legacy-model",
        "endpoint": "http://triton:8000/v2/models/legacy-model/infer",
        "api_key": None,
        "adapter_config": None,
    }
    service = BaseTaskService(service_info=service_info)
    service.payload_key = "input"

    async def _fake_run_inference(payload, serviceInfo):
        return PostProcessFormat(
            payload=payload, response_data=[{"target": "hi"}], source_texts=["hello"]
        )

    service.run_inference = _fake_run_inference
    service._adapter_config = None

    payload = {"input": [{"source": "hello"}], "config": {}}
    response = await service.process(payload, service_info)

    assert response["model"] == {
        "modelProvider": None,
        "modelVersion": None,
        "modelId": None,
        "language": [],
    }
