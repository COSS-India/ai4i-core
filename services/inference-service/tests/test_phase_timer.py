"""Unit tests for the per-request phase timer and its TIMING summary line."""

import asyncio
import logging
import time

import pytest

from config import settings
from trace.phase_timer import (
    add_ms,
    collect_phases,
    record_attr,
    start_root_phases,
    timed_phase,
)
from trace.request_span import format_timing_summary, traced_span


@pytest.fixture
def timing_on(monkeypatch):
    monkeypatch.setattr(settings, "PHASE_TIMING_ENABLED", True)
    start_root_phases()


# ── the gate ──────────────────────────────────────────────────────────────────

def test_disabled_timer_collects_nothing(monkeypatch):
    """When off, timed_phase must be a no-op with no contextvar writes."""
    monkeypatch.setattr(settings, "PHASE_TIMING_ENABLED", False)

    with timed_phase("validate_ms"):
        time.sleep(0.001)
    record_attr("cache_hit", True)

    assert collect_phases() == {}


# ── accumulation ──────────────────────────────────────────────────────────────

def test_sync_and_async_forms_both_record(timing_on):
    """timed_phase is used as both `with` and `async with` in the pipeline."""
    with timed_phase("validate_ms"):
        time.sleep(0.001)

    async def _run():
        async with timed_phase("preprocess_ms"):
            await asyncio.sleep(0.001)

    asyncio.run(_run())

    phases = collect_phases()
    assert phases["validate_ms"] > 0
    assert phases["preprocess_ms"] > 0


def test_repeated_entries_accumulate(timing_on):
    """per_item call_mode enters the same phase once per group; they must sum."""
    add_ms("triton_ms", 10.0)
    add_ms("triton_ms", 5.5)

    assert collect_phases()["triton_ms"] == pytest.approx(15.5)


def test_record_attr_stores_non_timing_values(timing_on):
    """cache_hit rides the same accumulator but is not a duration."""
    record_attr("cache_hit", False)

    assert collect_phases()["cache_hit"] is False


def test_start_root_phases_isolates_requests(timing_on):
    """A new root span must not inherit the previous request's timings."""
    add_ms("triton_ms", 10.0)
    start_root_phases()

    assert collect_phases() == {}


# ── summary formatting ────────────────────────────────────────────────────────

def test_summary_nests_subphases_under_their_parent():
    line = format_timing_summary({
        "total_time_ms": 42.0,
        "resolve_ms": 5.1, "mms_http_ms": 4.8,
        "run_inference_ms": 30.0, "triton_ms": 28.0,
    })

    assert line == (
        "TIMING total=42.0ms resolve=5.1 (mms_http=4.8) "
        "run_inference=30.0 (triton=28.0)"
    )


def test_summary_omits_absent_phases():
    """Only phases actually recorded are shown, so the line stays truthful."""
    line = format_timing_summary({"total_time_ms": 1.0, "validate_ms": 0.5})

    assert line == "TIMING total=1.0ms validate=0.5"
    assert "preprocess" not in line


def test_subphase_is_hidden_when_its_parent_is_absent():
    """A sub-phase with no parent key does not render.

    This is why the ASR fetch/decode split only became visible once
    preprocess_ms existed: without the parent, the sub-phases were collected
    onto the span but never reached the log line.
    """
    line = format_timing_summary({"total_time_ms": 1.0, "audio_fetch_ms": 0.3})

    assert "audio_fetch" not in line


def test_summary_appends_cache_hit_last():
    line = format_timing_summary({
        "total_time_ms": 1.0, "resolve_ms": 0.5, "cache_hit": True,
    })

    assert line.endswith("cache_hit=true")


# ── root span integration ─────────────────────────────────────────────────────

def test_root_span_merges_phases_and_logs_one_timing_line(monkeypatch, caplog):
    monkeypatch.setattr(settings, "PHASE_TIMING_ENABLED", True)

    with caplog.at_level(logging.INFO, logger="trace.request_span"):
        with traced_span("request", root=True, classify_status=True) as attrs:
            with timed_phase("validate_ms"):
                time.sleep(0.001)

    assert "validate_ms" in attrs
    timing_lines = [r for r in caplog.records if r.getMessage().startswith("TIMING")]
    assert len(timing_lines) == 1


def test_child_span_does_not_merge_or_log(monkeypatch, caplog):
    """Only the root span carries phases; model/ai-inference must not duplicate."""
    monkeypatch.setattr(settings, "PHASE_TIMING_ENABLED", True)
    start_root_phases()
    add_ms("triton_ms", 1.0)

    with caplog.at_level(logging.INFO, logger="trace.request_span"):
        with traced_span("model") as attrs:
            attrs["task_type"] = "NMT"

    assert "triton_ms" not in attrs
    assert not [r for r in caplog.records if r.getMessage().startswith("TIMING")]


def test_disabled_timer_logs_no_timing_line(monkeypatch, caplog):
    """A bare 'TIMING total=...' line would be noise on every request."""
    monkeypatch.setattr(settings, "PHASE_TIMING_ENABLED", False)

    with caplog.at_level(logging.INFO, logger="trace.request_span"):
        with traced_span("request", root=True, classify_status=True):
            with timed_phase("validate_ms"):
                time.sleep(0.001)

    assert not [r for r in caplog.records if r.getMessage().startswith("TIMING")]


def test_phases_still_merge_when_the_request_fails(monkeypatch, caplog):
    """A failed request is exactly when the stage breakdown matters most."""
    monkeypatch.setattr(settings, "PHASE_TIMING_ENABLED", True)

    with caplog.at_level(logging.INFO, logger="trace.request_span"):
        with pytest.raises(ValueError):
            with traced_span("request", root=True, classify_status=True):
                with timed_phase("validate_ms"):
                    time.sleep(0.001)
                raise ValueError("bad input")

    assert [r for r in caplog.records if r.getMessage().startswith("TIMING")]
