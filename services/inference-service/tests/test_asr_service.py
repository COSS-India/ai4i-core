"""Unit tests for ASRTaskService — validation, audio helpers, byte decoding."""

import base64
import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── validate_request ──────────────────────────────────────────────────────────

async def test_validate_accepts_camelCase_sourceLanguage(asr_service):
    payload = {
        "audio": [{"audioContent": base64.b64encode(b"x").decode()}],
        "config": {"language": {"sourceLanguage": "en"}},
    }
    await asr_service.validate_request(payload)


async def test_validate_accepts_snakeCase_sourceLanguage(asr_service):
    payload = {
        "audio": [{"audio_content": base64.b64encode(b"x").decode()}],
        "config": {"language": {"source_language": "hi"}},
    }
    await asr_service.validate_request(payload)


async def test_validate_rejects_missing_sourceLanguage(asr_service):
    payload = {
        "audio": [{"audioContent": base64.b64encode(b"x").decode()}],
        "config": {"language": {}},
    }
    with pytest.raises(ValueError, match="sourceLanguage is required"):
        await asr_service.validate_request(payload)


async def test_validate_rejects_empty_audio_list(asr_service):
    payload = {
        "audio": [],
        "config": {"language": {"sourceLanguage": "en"}},
    }
    with pytest.raises(ValueError, match="audio list cannot be empty"):
        await asr_service.validate_request(payload)


async def test_validate_rejects_audio_item_without_content_or_uri(asr_service):
    payload = {
        "audio": [{}],
        "config": {"language": {"sourceLanguage": "en"}},
    }
    with pytest.raises(ValueError, match="audio_content or audio_uri"):
        await asr_service.validate_request(payload)


# ── _stereo_to_mono ───────────────────────────────────────────────────────────

def test_stereo_to_mono_averages_channels(asr_service):
    stereo = np.array([[0.5, -0.5], [1.0, 0.0]], dtype=np.float32)
    mono = asr_service._stereo_to_mono(stereo)
    assert mono.ndim == 1
    np.testing.assert_allclose(mono, [0.0, 0.5], atol=1e-6)


def test_stereo_to_mono_is_noop_for_mono_input(asr_service):
    mono = np.array([0.5, 1.0, -0.5], dtype=np.float32)
    result = asr_service._stereo_to_mono(mono)
    np.testing.assert_array_equal(result, mono)


# ── _resample ─────────────────────────────────────────────────────────────────

def test_resample_is_noop_when_rates_equal(asr_service):
    data = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    result = asr_service._resample(data, 16000, 16000)
    np.testing.assert_array_equal(result, data)


def test_resample_halves_length_when_target_is_half(asr_service):
    data = np.ones(32000, dtype=np.float32)
    result = asr_service._resample(data, 32000, 16000)
    assert len(result) == 16000


# ── _equalize_amplitude ───────────────────────────────────────────────────────

def test_equalize_amplitude_normalizes_peak_to_one(asr_service):
    audio = np.array([0.2, 0.5, -0.4, 0.8], dtype=np.float32)
    result = asr_service._equalize_amplitude(audio)
    assert np.max(np.abs(result)) == pytest.approx(1.0)


def test_equalize_amplitude_is_noop_for_silent_audio(asr_service):
    silent = np.zeros(100, dtype=np.float32)
    result = asr_service._equalize_amplitude(silent)
    np.testing.assert_array_equal(result, silent)


# ── _get_audio_bytes ──────────────────────────────────────────────────────────

async def test_get_audio_bytes_decodes_base64_content(asr_service):
    raw = b"fake audio bytes"
    encoded = base64.b64encode(raw).decode()
    result = await asr_service._get_audio_bytes({"audioContent": encoded})
    assert result == raw


async def test_get_audio_bytes_accepts_snake_case_key(asr_service):
    raw = b"more audio"
    encoded = base64.b64encode(raw).decode()
    result = await asr_service._get_audio_bytes({"audio_content": encoded})
    assert result == raw


async def test_get_audio_bytes_raises_when_neither_content_nor_uri(asr_service):
    with pytest.raises(ValueError, match="audio_content or audio_uri"):
        await asr_service._get_audio_bytes({})


# ── _decode_audio_bytes ───────────────────────────────────────────────────────

async def test_decode_audio_bytes_raises_for_invalid_bytes(asr_service):
    with pytest.raises(ValueError, match="unable to decode audio"):
        await asr_service._decode_audio_bytes(b"not valid audio data at all")
