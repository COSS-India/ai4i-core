"""Unit tests for TTSTaskService — sampling rate/duration bounds, text chunking,
Triton output extraction, and audio processing helpers."""

import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── _validated_sample_rate ────────────────────────────────────────────────────

def test_validated_sample_rate_accepts_mid_range(tts_service):
    assert tts_service._validated_sample_rate({"samplingRate": 22050}) == 22050


def test_validated_sample_rate_accepts_minimum_boundary(tts_service):
    assert tts_service._validated_sample_rate({"samplingRate": 8000}) == 8000


def test_validated_sample_rate_accepts_maximum_boundary(tts_service):
    assert tts_service._validated_sample_rate({"samplingRate": 48000}) == 48000


def test_validated_sample_rate_rejects_below_minimum(tts_service):
    with pytest.raises(ValueError, match="samplingRate must be between"):
        tts_service._validated_sample_rate({"samplingRate": 7999})


def test_validated_sample_rate_rejects_above_maximum(tts_service):
    with pytest.raises(ValueError, match="samplingRate must be between"):
        tts_service._validated_sample_rate({"samplingRate": 48001})


def test_validated_sample_rate_defaults_to_triton_rate_when_absent(tts_service):
    assert tts_service._validated_sample_rate({}) == 22050


def test_validated_sample_rate_rejects_non_integer_string(tts_service):
    with pytest.raises(ValueError, match="must be an integer"):
        tts_service._validated_sample_rate({"samplingRate": "abc"})


# ── _validated_duration ───────────────────────────────────────────────────────

def test_validated_duration_returns_none_for_none(tts_service):
    assert tts_service._validated_duration(None) is None


def test_validated_duration_accepts_valid_value(tts_service):
    assert tts_service._validated_duration(30.0) == pytest.approx(30.0)


def test_validated_duration_rejects_zero(tts_service):
    with pytest.raises(ValueError, match="audioDuration must be between"):
        tts_service._validated_duration(0)


def test_validated_duration_rejects_negative(tts_service):
    with pytest.raises(ValueError, match="audioDuration must be between"):
        tts_service._validated_duration(-1.0)


def test_validated_duration_rejects_above_max(tts_service):
    with pytest.raises(ValueError, match="audioDuration must be between"):
        tts_service._validated_duration(301.0)


def test_validated_duration_rejects_non_number_string(tts_service):
    with pytest.raises(ValueError, match="audioDuration must be a number"):
        tts_service._validated_duration("long")


# ── _chunk_text ───────────────────────────────────────────────────────────────

def test_chunk_text_returns_unchanged_for_short_text(tts_service):
    result = tts_service._chunk_text("Hello world", max_length=400)
    assert result == ["Hello world"]


def test_chunk_text_returns_single_empty_string_for_empty_input(tts_service):
    result = tts_service._chunk_text("")
    assert result == [""]


def test_chunk_text_splits_at_sentence_period(tts_service):
    # "A" * 300 + ". " + "B" * 300 = 602 chars, split required at max_length=400
    text = "A" * 300 + ". " + "B" * 300
    result = tts_service._chunk_text(text, max_length=400)
    assert len(result) == 2
    assert result[0].endswith(".")


def test_chunk_text_splits_at_space_when_no_punctuation(tts_service):
    # many short words joined: total > max_length
    text = " ".join(["word"] * 20)  # "word word word ..." ~99 chars
    result = tts_service._chunk_text(text, max_length=20)
    for chunk in result:
        assert len(chunk) <= 20


# ── convert_triton_output_to_task_format ─────────────────────────────────────

async def test_extract_output_generated_audio_converts_to_int16(tts_service):
    triton_output = {
        "outputs": [
            {"name": "OUTPUT_GENERATED_AUDIO", "data": [0.5, -0.5, 1.0, -1.0]}
        ]
    }
    result = await tts_service.convert_triton_output_to_task_format(triton_output)
    assert len(result) == 1
    samples = result[0]["samples"]
    assert samples.dtype == np.int16
    assert len(samples) == 4
    assert samples[2] == 32767   # 1.0 * 32767 clipped
    assert samples[3] == np.clip(int(-1.0 * 32767), -32768, 32767)


async def test_extract_output_raises_when_tensor_missing(tts_service):
    with pytest.raises(RuntimeError, match="OUTPUT_GENERATED_AUDIO not found"):
        await tts_service.convert_triton_output_to_task_format({"outputs": []})


# ── _append_silence ───────────────────────────────────────────────────────────

def test_append_silence_pads_to_target_duration(tts_service):
    audio = np.zeros(8000, dtype=np.int16)   # 1 s at 8 kHz
    result = tts_service._append_silence(audio, 8000, 2.0)
    assert len(result) == 16000


def test_append_silence_is_noop_when_already_at_target_length(tts_service):
    audio = np.zeros(16000, dtype=np.int16)
    result = tts_service._append_silence(audio, 8000, 1.0)  # 2 s already ≥ 1 s
    assert len(result) == len(audio)


# ── _stretch_audio ────────────────────────────────────────────────────────────

def test_stretch_audio_produces_correct_sample_count(tts_service):
    audio = np.zeros(16000, dtype=np.int16)  # 1 s at 16 kHz
    result = tts_service._stretch_audio(audio, 16000, 2.0)
    assert len(result) == 32000


# ── preprocess_input (chunking metadata) ─────────────────────────────────────

async def test_preprocess_annotates_chunks_with_gender_and_language(tts_service):
    payload = {
        "input": [{"source": "Hello world"}],
        "config": {"language": {"sourceLanguage": "hi"}, "gender": "male"},
    }
    result = await tts_service.preprocess_input(payload)
    items = result["input"]
    assert len(items) == 1
    assert items[0]["gender"] == "male"
    assert items[0]["language_id"] == "hi"
    assert items[0]["_item_index"] == 0
