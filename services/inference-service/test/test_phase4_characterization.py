"""Characterization tests for TTS, ASR, and Speaker Diarization responses.

These pin the exact client-facing response of process() for each service, so
the Phase 4 produce_result / build_envelope split can be proven byte-identical.
They mock only the HTTP call to Triton; the real preprocess, mapper, run, and
postprocess run unchanged.

Run from the inference-service root:
    PYTHONPATH=. pytest test/test_phase4_characterization.py
"""

import base64
import sys
from io import BytesIO
from unittest.mock import AsyncMock, patch

import numpy as np
import scipy.io.wavfile as wav_io

sys.path.insert(0, ".")


def _post_json_returning(triton_response: dict) -> AsyncMock:
    """Patch target: HTTPServiceClient.post_json always returns this response."""
    return AsyncMock(return_value=triton_response)


# ════════════════════════════════════════════════════════════════════════════
# TTS — custom postprocess (waveform merge + encode + audio envelope)
# ════════════════════════════════════════════════════════════════════════════

_TTS_ADAPTER_CONFIG = {
    "version": "1.0",
    "model_version": "1",
    "inputs": [
        {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [1], "value_path": "input.source"},
        {"tensor": "INPUT_SPEAKER_ID", "dtype": "BYTES", "shape": [1], "value_path": "input.gender"},
        {"tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [1], "value_path": "input.language_id"},
    ],
    "outputs": [
        {"tensor": "OUTPUT_GENERATED_AUDIO", "dtype": "FP32", "maps_to": "audio_data"},
    ],
}

_TTS_SERVICE_INFO = {
    "name": "tts-gpu",
    "endpoint": "http://triton:8000/v2/models/tts-gpu/infer",
    "api_key": None,
    "adapter_config": _TTS_ADAPTER_CONFIG,
}

# Triton returns FP32 [-1, 1] waveform samples at 22050 Hz.
_TTS_FP32 = [0.0, 0.25, -0.25, 0.5, -0.5]
_TTS_TRITON_RESPONSE = {
    "outputs": [{"name": "OUTPUT_GENERATED_AUDIO", "datatype": "FP32", "shape": [5], "data": _TTS_FP32}],
}


async def test_tts_response_characterization():
    from services.tts_service import TTSTaskService

    service = TTSTaskService(service_info=_TTS_SERVICE_INFO)
    payload = {
        "input": [{"source": "नमस्ते"}],
        "config": {
            "language": {"sourceLanguage": "hi"},
            "gender": "female",
            "samplingRate": 22050,   # == _TRITON_SAMPLE_RATE -> no resample
            "audioFormat": "wav",    # wav -> no ffmpeg dependency
        },
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=_post_json_returning(_TTS_TRITON_RESPONSE),
    ):
        response = await service.process(payload)

    # Exact envelope shape (this is what Phase 4 must preserve).
    assert set(response.keys()) == {"audio", "config"}

    expected_samples = np.clip(np.array(_TTS_FP32, dtype=np.float32) * 32767, -32768, 32767).astype(np.int16)
    expected_duration = len(expected_samples) / 22050
    assert response["config"] == {
        "language": {"sourceLanguage": "hi", "sourceScriptCode": None},
        "audioFormat": "wav",
        "encoding": "base64",
        "samplingRate": 22050,
        "audioDuration": expected_duration,
    }

    assert len(response["audio"]) == 1
    item = response["audio"][0]
    assert set(item.keys()) == {"audioContent", "audioUri", "audioDuration"}
    assert item["audioUri"] is None
    assert item["audioDuration"] == expected_duration

    # audioContent decodes to a 22050 Hz wav carrying the expected int16 samples.
    rate, decoded = wav_io.read(BytesIO(base64.b64decode(item["audioContent"])))
    assert rate == 22050
    assert np.array_equal(decoded, expected_samples)


# ════════════════════════════════════════════════════════════════════════════
# ASR — audio preprocess + per_item + default postprocess (real DB config shape)
# ════════════════════════════════════════════════════════════════════════════

_ASR_ADAPTER_CONFIG = {
    "version": "1.0",
    "model_version": "1",
    "inputs": [
        {"tensor": "AUDIO_SIGNAL", "dtype": "FP32", "shape": [-1, -1], "value_path": "audio.samples"},
        {"tensor": "NUM_SAMPLES", "dtype": "INT32", "shape": [-1, 1], "value_path": "audio.num_samples"},
        {"tensor": "LANG_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.source_language"},
    ],
    "outputs": [
        {"tensor": "TRANSCRIPTS", "dtype": "BYTES", "maps_to": "transcript"},
    ],
}

_ASR_SERVICE_INFO = {
    "name": "asr-gpu",
    "endpoint": "http://triton:8000/v2/models/asr-gpu/infer",
    "api_key": None,
    "adapter_config": _ASR_ADAPTER_CONFIG,
}


def _make_wav_base64(sample_rate: int = 16000, num_samples: int = 320) -> str:
    """A tiny decodable mono int16 wav, base64-encoded (silence is fine)."""
    samples = np.zeros(num_samples, dtype=np.int16)
    buf = BytesIO()
    wav_io.write(buf, sample_rate, samples)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


async def test_asr_response_characterization():
    from services.asr_service import ASRTaskService

    service = ASRTaskService(service_info=_ASR_SERVICE_INFO)
    payload = {
        "audio": [{"audioContent": _make_wav_base64()}],
        "config": {"language": {"sourceLanguage": "en"}},
    }
    triton_response = {
        "outputs": [{"name": "TRANSCRIPTS", "datatype": "BYTES", "shape": [1, 1], "data": ["hello world"]}],
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=_post_json_returning(triton_response),
    ):
        response = await service.process(payload)

    # Default postprocess path: transcript item paired with an (empty) source,
    # plus the echoed config. This is the current behavior under the DB config
    # shape (no response_key declared).
    assert set(response.keys()) == {"output", "config"}
    assert response["output"] == [{"transcript": "hello world", "source": ""}]
    assert response["config"] == {"language": {"sourceLanguage": "en"}}


# ════════════════════════════════════════════════════════════════════════════
# Speaker Diarization — custom postprocess (JSON parse + envelope)
# ════════════════════════════════════════════════════════════════════════════

# Speaker Diarization migrated to v2 (AI4IDS-1981): aggregation is now the
# output_transform; the service class is empty. Same task-type output as v1.
_SD_T = (
    '{ "taskType": "speaker-diarization", "output": [ $map(tensors.DIARIZATION_RESULT, '
    'function($dr){ ( $segs := $sort($dr.segments, function($a,$b){$a.start_time > $b.start_time})'
    '.{"start": start_time, "end": end_time, '
    '"duration": ($exists(duration) ? duration : end_time - start_time), "speaker": speaker}; '
    '{"total_segments": $count($segs), "num_speakers": $count($distinct($segs.speaker)), '
    '"speakers": $sort($distinct($segs.speaker)), "segments": $segs} ) }) ], '
    '"config": { "serviceId": request.config.serviceId, '
    '"language": ($exists(request.config.language) ? request.config.language : null) } }'
)

_SD_ADAPTER_CONFIG = {
    "schema_version": "2.0",
    "model_version": "1",
    "inputs": [
        {"tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "audio.audio_content"},
        {"tensor": "NUM_SPEAKERS", "dtype": "BYTES", "shape": [1, 1], "value_path": "request.config.num_speakers"},
    ],
    "outputs": [{"tensor": "DIARIZATION_RESULT", "is_json": True}],
    "output_transform": _SD_T,
}

_SD_SERVICE_INFO = {
    "name": "sd-gpu",
    "endpoint": "http://triton:8000/v2/models/sd-gpu/infer",
    "api_key": None,
    "adapter_config": _SD_ADAPTER_CONFIG,
}


async def test_speaker_diarization_response_characterization():
    from services.speaker_diarization_service import SpeakerDiarizationTaskService

    service = SpeakerDiarizationTaskService(service_info=_SD_SERVICE_INFO)
    payload = {
        "audio": [{"audioContent": base64.b64encode(b"fakeaudio").decode("utf-8")}],
        "config": {"serviceId": "sd-1", "numSpeakers": "2"},
    }
    diarization_json = (
        '{"segments": ['
        '{"start_time": 1.5, "end_time": 3.0, "speaker": "spk_1"},'
        '{"start_time": 0.0, "end_time": 1.5, "speaker": "spk_0", "duration": 1.5}'
        ']}'
    )
    triton_response = {
        "outputs": [{"name": "DIARIZATION_RESULT", "datatype": "BYTES", "shape": [1, 1], "data": [diarization_json]}],
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=_post_json_returning(triton_response),
    ):
        response = await service.process(payload)

    assert response == {
        "taskType": "speaker-diarization",
        "output": [{
            "total_segments": 2,
            "num_speakers": 2,
            "speakers": ["spk_0", "spk_1"],
            "segments": [
                {"start": 0.0, "end": 1.5, "duration": 1.5, "speaker": "spk_0"},
                {"start": 1.5, "end": 3.0, "duration": 1.5, "speaker": "spk_1"},
            ],
        }],
        "config": {"serviceId": "sd-1", "language": None},
    }
