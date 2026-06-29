"""Tests for numpy-aware Triton input materialization (ASR float PCM path)."""

import sys

import numpy as np
import pytest

sys.path.insert(0, ".")

from services.base.config_mapper import GenericTritonMapper


ASR_ADAPTER = {
    "version": "1.0",
    "model_version": "1",
    "inputs": [
        {
            "dtype": "FP32",
            "shape": [-1, -1],
            "tensor": "AUDIO_SIGNAL",
            "value_path": "audio.samples",
        },
        {
            "dtype": "INT32",
            "shape": [-1, 1],
            "tensor": "NUM_SAMPLES",
            "value_path": "audio.num_samples",
        },
        {
            "dtype": "BYTES",
            "shape": [-1, 1],
            "tensor": "LANG_ID",
            "value_path": "request.config.language.source_language",
        },
    ],
    "outputs": [{"dtype": "BYTES", "tensor": "TRANSCRIPTS", "maps_to": "transcript"}],
}


def test_fp32_ndarray_materializes_without_python_per_sample_cast():
    mapper = GenericTritonMapper(ASR_ADAPTER)
    samples = np.linspace(-1.0, 1.0, num=240_000, dtype=np.float32)
    input_data = [{"samples": samples, "num_samples": len(samples)}]
    config = {"language": {"source_language": "hi"}}

    def context_builder(item, index, cfg):
        return {
            "audio": {
                "samples": item["samples"],
                "num_samples": item["num_samples"],
            }
        }

    triton_inputs, output_names = mapper.render_inputs(
        input_data, config, context_builder=context_builder
    )

    audio = triton_inputs["AUDIO_SIGNAL"]
    assert audio["dtype"] == "FP32"
    assert audio["shape"] == [1, 240_000]
    assert len(audio["data"]) == 240_000
    assert audio["data"][0] == pytest.approx(-1.0)
    assert audio["data"][-1] == pytest.approx(1.0)
    assert triton_inputs["NUM_SAMPLES"]["data"] == [240_000]
    assert triton_inputs["LANG_ID"]["data"] == ["hi"]
    assert output_names == ["TRANSCRIPTS"]


def test_context_builder_accepts_ndarray_samples():
    """Regression: `samples or []` is invalid for numpy arrays (ambiguous truth)."""
    from services.asr_service import ASRTaskService

    samples = np.zeros(1024, dtype=np.float32)
    item = {"samples": samples, "num_samples": 1024, "sample_rate": 16000}
    ctx = ASRTaskService(service_info={})._triton_context_builder()(item, 0, {})
    assert ctx["audio"]["samples"] is samples
    assert ctx["audio"]["num_samples"] == 1024
