"""Gate the migrated v2 adapter_configs against the v1 golden outputs.

For each service migrated to the v2 (JSONata) schema in AI4IDS-1981 Phase 4,
this asserts the v2 config drives process() to the same task-type output that
the v1 characterization tests pinned. The v2 configs here mirror what the
Alembic migrations write to mm_models.adapter_config.
"""

import base64
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, ".")

_B64 = base64.b64encode(b"fake").decode()

_OCR_T = ('{ "output": [ $map(tensors.OUTPUT_TEXT, function($t){ '
          '{"source": $t, "target": ""} }) ], "config": request.config }')
_TRANSLIT_T = ('( $inp := inputs; { "output": [ $map(tensors.OUTPUT_TEXT, function($t,$i){ '
               '{"source": ($exists($inp[$i].source) ? $inp[$i].source : ""), "target": $t} }) ] } )')
_LANGDET_T = ('( $inp := inputs; { "output": [ $map(tensors.OUTPUT_TEXT, function($p,$i){ '
              '{"source": $inp[$i].source, "langPrediction": [$p]} }) ] } )')


async def _run(mod, cls, cfg, payload, triton):
    import importlib
    m = importlib.import_module(mod)
    svc = getattr(m, cls)(service_info={
        "name": "m", "endpoint": "http://t/m/infer", "api_key": None, "adapter_config": cfg})
    with patch("utils.http_client.HTTPServiceClient.post_json",
               new=AsyncMock(return_value=triton)):
        return await svc.process(payload)


async def test_ocr_v2_matches_golden():
    out = await _run(
        "services.ocr_service", "OCRTaskService",
        {"schema_version": "2.0", "model_version": "1",
         "inputs": [{"tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1],
                     "value_path": "input.image_content"}],
         "outputs": [{"tensor": "OUTPUT_TEXT"}], "output_transform": _OCR_T},
        {"image": [{"imageContent": _B64, "imageFormat": "png"}],
         "config": {"language": {"sourceLanguage": "en"}}},
        {"outputs": [{"name": "OUTPUT_TEXT", "data": ["Hello World"]}]},
    )
    assert out == {"output": [{"source": "Hello World", "target": ""}],
                   "config": {"language": {"sourceLanguage": "en"}}}


async def test_transliteration_v2_matches_golden():
    out = await _run(
        "services.transliteration_service", "TransliterationTaskService",
        {"schema_version": "2.0", "model_version": "1",
         "inputs": [
             {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1], "value_path": "input.source"},
             {"tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1],
              "value_path": "request.config.language.sourceLanguage"},
             {"tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1],
              "value_path": "request.config.language.targetLanguage"},
             {"tensor": "IS_WORD_LEVEL", "dtype": "BOOL", "shape": [-1],
              "value_path": "request.config.is_word_level"},
             {"tensor": "TOP_K", "dtype": "UINT8", "shape": [-1], "value_path": "request.config.top_k"}],
         "outputs": [{"tensor": "OUTPUT_TEXT"}], "output_transform": _TRANSLIT_T},
        {"input": [{"source": "namaste"}],
         "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "en"},
                    "numSuggestions": 0, "isSentence": False}},
        {"outputs": [{"name": "OUTPUT_TEXT", "data": ["नमस्ते"]}]},
    )
    assert out == {"output": [{"source": "namaste", "target": "नमस्ते"}]}


async def test_language_detection_v2_matches_golden():
    out = await _run(
        "services.language_detection_service", "LanguageDetectionTaskService",
        {"schema_version": "2.0", "model_version": "1",
         "inputs": [{"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1],
                     "value_path": "input.source"}],
         "outputs": [{"tensor": "OUTPUT_TEXT", "is_json": True}], "output_transform": _LANGDET_T},
        {"input": [{"source": "hello world"}], "config": {"language": {"sourceLanguage": "hi"}}},
        {"outputs": [{"name": "OUTPUT_TEXT", "data": ['{"langCode":"en","score":0.99}']}]},
    )
    assert out == {"output": [{"source": "hello world",
                               "langPrediction": [{"langCode": "en", "score": 0.99}]}]}
