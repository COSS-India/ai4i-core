"""Contract test: every stub must convert under the real adapter_config.

Why this exists
---------------
In stub mode the Triton call is replaced, but everything after it still runs.
convert_triton_output_to_task_format is driven entirely by adapter_config, and
GenericTritonMapper.map_outputs raises RuntimeError when a declared output
tensor is absent from the response. So a stub whose tensor names drift from the
registered config does not fail loudly at startup: the endpoint returns 500 on
every request.

That is worse than it sounds for a load test. The error path short-circuits
before conversion and postprocessing, so it is *faster* than the success path.
A drifted stub produces a fast, clean-looking run that measures nothing.

Fixture provenance
------------------
tests/fixtures/mm_models_adapter_configs.json is a verbatim dump of
    ai4iplatform_core -> mm_models -> inference_endpoint -> 'adapter_config'
It was verified byte-identical to what migrations a1f2e3d4c5b6 (base seed) and
d7b2c4e6f8a1 (transforms + response envelopes) produce, so the two sources of
truth agreed at capture time.

To refresh after an adapter_config change:
    SELECT name, inference_endpoint->'adapter_config'
    FROM mm_models WHERE inference_endpoint->'adapter_config' IS NOT NULL;

Held as a fixture rather than read from the DB or parsed out of the migration
files, so the test needs no database and does not break when a migration is
renamed.
"""

import json
import pathlib

import pytest

from config import settings
from response_test.stub_dispatcher import get_stub_response
from services.base.config_mapper import GenericTritonMapper

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mm_models_adapter_configs.json"
ADAPTER_CONFIGS = json.loads(_FIXTURE.read_text())

# mm_models.name -> the TaskService that serves it.
MODEL_TO_SERVICE = {
    "ald":                 "AudioLanguageDetectionTaskService",
    "asr-am-ensemble":     "ASRTaskService",
    "indiclid":            "LanguageDetectionTaskService",
    "indictrans":          "NMTTaskService",
    "lang-diarization":    "LanguageDiarizationTaskService",
    "ner":                 "NERTaskService",
    "speaker-diarization": "SpeakerDiarizationTaskService",
    "surya-ocr":           "OCRTaskService",
    "transliteration":     "TransliterationTaskService",
    "tts":                 "TTSTaskService",
}

# Size buckets exercised for every model: below, inside and above the
# SMALL/MEDIUM thresholds, since each returns a different fixture.
_SIZES = [10, 500, 1500]


@pytest.fixture
def stub_mode(monkeypatch):
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", True)


def _stub_for(service, length):
    return get_stub_response(service, [{"name": "IN", "data": ["x" * length]}])


def test_fixture_covers_every_stubbed_service():
    """A stub with no config entry here would go unverified."""
    from response_test.stub_dispatcher import _STUBS

    assert set(MODEL_TO_SERVICE.values()) == set(_STUBS)
    assert set(MODEL_TO_SERVICE) == set(ADAPTER_CONFIGS)


@pytest.mark.parametrize("model", sorted(MODEL_TO_SERVICE))
@pytest.mark.parametrize("length", _SIZES)
def test_stub_emits_every_declared_output_tensor(model, length, stub_mode):
    """map_outputs raises RuntimeError on a missing tensor, which becomes a 500."""
    config = ADAPTER_CONFIGS[model]
    stub = _stub_for(MODEL_TO_SERVICE[model], length)

    declared = {out["tensor"] for out in config["outputs"]}
    emitted = {out["name"] for out in stub["outputs"]}

    assert declared <= emitted, (
        f"{model}: adapter_config declares {sorted(declared - emitted)} "
        f"but the stub emits only {sorted(emitted)}"
    )


@pytest.mark.parametrize("model", sorted(set(MODEL_TO_SERVICE) - {"tts"}))
@pytest.mark.parametrize("length", _SIZES)
def test_stub_converts_under_the_real_config(model, length, stub_mode):
    """Full conversion, including the json_parse transforms on four models.

    TTS is excluded: it overrides convert_triton_output_to_task_format because
    the generic mapper would explode a waveform into one item per sample. It is
    covered by its own test below, through the converter it actually uses.
    """
    config = ADAPTER_CONFIGS[model]
    stub = _stub_for(MODEL_TO_SERVICE[model], length)

    mapper = GenericTritonMapper(config)
    items = mapper.to_output_items(mapper.map_outputs(stub))

    assert items
    for out in config["outputs"]:
        assert out["maps_to"] in items[0]


@pytest.mark.parametrize("length", _SIZES)
@pytest.mark.asyncio
async def test_tts_stub_converts_through_its_own_converter(length, stub_mode):
    """TTS returns one item holding the whole waveform, not one item per sample."""
    from services.tts_service import TTSTaskService

    service = TTSTaskService(service_info={
        "name": "tts", "endpoint": "http://triton.invalid:8000",
        "api_key": None, "adapter_config": ADAPTER_CONFIGS["tts"],
    })
    stub = _stub_for("TTSTaskService", length)

    items = await service.convert_triton_output_to_task_format(stub)

    assert len(items) == 1
    assert items[0]["samples"].dtype.name == "int16"
    assert len(items[0]["samples"]) > 0
