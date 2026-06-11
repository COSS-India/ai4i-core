"""Unit tests for SpeakerDiarizationTaskService — postprocess_output segment
parsing, speaker counting, and sort ordering."""

import json
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_result(segments, config=None):
    from services.base.task_service import PostProcessFormat
    diarization_json = json.dumps({"segments": segments})
    return PostProcessFormat(
        payload={"config": config or {}},
        response_data=[{"diarization_json": diarization_json}],
        source_texts=[],
    )


# ── postprocess_output ────────────────────────────────────────────────────────

async def test_postprocess_parses_segments_and_speaker_list(speaker_diarization_service):
    result = _make_result([
        {"start_time": 0.0, "end_time": 2.5, "duration": 2.5, "speaker": "speaker-0"},
        {"start_time": 2.5, "end_time": 5.0, "duration": 2.5, "speaker": "speaker-1"},
    ])
    output = await speaker_diarization_service.postprocess_output(result)
    assert output["taskType"] == "speaker-diarization"
    item = output["output"][0]
    assert item["total_segments"] == 2
    assert item["num_speakers"] == 2
    assert sorted(item["speakers"]) == ["speaker-0", "speaker-1"]


async def test_postprocess_handles_null_diarization_data(speaker_diarization_service):
    from services.base.task_service import PostProcessFormat
    result = PostProcessFormat(
        payload={"config": {}},
        response_data=[{"diarization_json": None}],
        source_texts=[],
    )
    output = await speaker_diarization_service.postprocess_output(result)
    item = output["output"][0]
    assert item["total_segments"] == 0
    assert item["num_speakers"] == 0
    assert item["segments"] == []


async def test_postprocess_sorts_segments_by_start_time(speaker_diarization_service):
    # segments arrive out of chronological order
    result = _make_result([
        {"start_time": 3.0, "end_time": 5.0, "duration": 2.0, "speaker": "speaker-0"},
        {"start_time": 0.0, "end_time": 2.0, "duration": 2.0, "speaker": "speaker-1"},
    ])
    output = await speaker_diarization_service.postprocess_output(result)
    segments = output["output"][0]["segments"]
    assert segments[0]["start"] < segments[1]["start"]


async def test_postprocess_counts_only_unique_speakers(speaker_diarization_service):
    # speaker-0 appears in two segments; should count as one unique speaker
    result = _make_result([
        {"start_time": 0.0, "end_time": 1.0, "duration": 1.0, "speaker": "speaker-0"},
        {"start_time": 1.0, "end_time": 2.0, "duration": 1.0, "speaker": "speaker-0"},
        {"start_time": 2.0, "end_time": 3.0, "duration": 1.0, "speaker": "speaker-1"},
    ])
    output = await speaker_diarization_service.postprocess_output(result)
    item = output["output"][0]
    assert item["total_segments"] == 3
    assert item["num_speakers"] == 2


async def test_postprocess_uses_duration_from_segment_field(speaker_diarization_service):
    result = _make_result([
        {"start_time": 1.0, "end_time": 3.0, "duration": 2.0, "speaker": "speaker-0"},
    ])
    output = await speaker_diarization_service.postprocess_output(result)
    segment = output["output"][0]["segments"][0]
    assert segment["duration"] == pytest.approx(2.0)


async def test_postprocess_falls_back_to_computed_duration(speaker_diarization_service):
    # no duration field — should compute end - start
    result = _make_result([
        {"start_time": 1.0, "end_time": 4.0, "speaker": "speaker-0"},
    ])
    output = await speaker_diarization_service.postprocess_output(result)
    segment = output["output"][0]["segments"][0]
    assert segment["duration"] == pytest.approx(3.0)


async def test_postprocess_includes_service_id_in_config(speaker_diarization_service):
    from services.base.task_service import PostProcessFormat
    result = PostProcessFormat(
        payload={"config": {"serviceId": "sd-v2", "language": {"sourceLanguage": "en"}}},
        response_data=[{"diarization_json": json.dumps({"segments": []})}],
        source_texts=[],
    )
    output = await speaker_diarization_service.postprocess_output(result)
    assert output["config"]["serviceId"] == "sd-v2"
