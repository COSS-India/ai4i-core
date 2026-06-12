"""End-to-end test of a v2 (JSONata) adapter_config through process() (AI4IDS-1981).

Drives NMTTaskService with a v2 config and only the Triton HTTP mocked, proving
the schema_version dispatch wires up end to end: v1 input render, JSONata output
transform, and the same task-type output a v1 NMT config produces. v1 configs
are exercised by the existing suites; this proves the v2 path is live.
"""

import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, ".")

_V2_NMT_TRANSFORM = (
    "( $inp := inputs; "
    "{ 'output': [ $map(tensors.OUTPUT_TEXT, function($t, $i) "
    "{ {'source': $inp[$i].source, 'target': $t} }) ] } )"
)

_V2_NMT_SERVICE_INFO = {
    "service_id": "indictrans-v2",
    "name": "indictrans-gpu",
    "endpoint": "http://triton:8000/v2/models/indictrans/infer",
    "api_key": None,
    "adapter_config": {
        "schema_version": "2.0",
        "model_version": "1",
        "inputs": [
            {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
            {"tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1],
             "value_path": "request.config.language.source_language"},
            {"tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1],
             "value_path": "request.config.language.target_language"},
        ],
        "outputs": [{"tensor": "OUTPUT_TEXT"}],
        "output_transform": _V2_NMT_TRANSFORM,
    },
}


async def test_v2_nmt_process_end_to_end():
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=_V2_NMT_SERVICE_INFO)
    payload = {
        "input": [{"source": "Hello"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }
    triton_response = {
        "outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["नमस्ते"]}]
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=triton_response),
    ):
        response = await service.process(payload)

    # Same task-type output a v1 NMT config produces, via the JSONata path.
    assert response == {"output": [{"source": "Hello", "target": "नमस्ते"}]}


async def test_v2_nmt_multi_input_batch():
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=_V2_NMT_SERVICE_INFO)
    payload = {
        "input": [{"source": "Hello"}, {"source": "Goodbye"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }
    # NMT is batch mode: one Triton call returns both translations.
    triton_response = {
        "outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES", "shape": [2, 1],
                     "data": ["नमस्ते", "अलविदा"]}]
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=triton_response),
    ):
        response = await service.process(payload)

    assert response == {"output": [
        {"source": "Hello", "target": "नमस्ते"},
        {"source": "Goodbye", "target": "अलविदा"},
    ]}
