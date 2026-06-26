"""Unit tests for the per-block phase timer (trace/phase_timer.py)."""

import pytest

from config import settings
from trace import phase_timer


@pytest.fixture
def timing_on():
    """Enable phase timing for the test, restore the prior value after."""
    previous = settings.PHASE_TIMING_ENABLED
    settings.PHASE_TIMING_ENABLED = True
    phase_timer.start_root_phases()  # fresh per-request accumulator
    yield
    settings.PHASE_TIMING_ENABLED = previous


def test_timed_phase_accumulates_across_repeats(timing_on):
    """The same phase name entered twice sums into one total (per-item loops)."""
    with phase_timer.timed_phase("build_payload_ms"):
        pass
    with phase_timer.timed_phase("build_payload_ms"):
        pass

    phases = phase_timer.collect_phases()
    assert "build_payload_ms" in phases
    assert phases["build_payload_ms"] >= 0.0


@pytest.mark.asyncio
async def test_async_timed_phase_and_attrs(timing_on):
    """async with records a duration; record_attr stores a flag alongside it."""
    async with phase_timer.timed_phase("triton_ms"):
        pass
    phase_timer.record_attr("cache_hit", True)

    phases = phase_timer.collect_phases()
    assert "triton_ms" in phases
    assert phases["cache_hit"] is True


def test_disabled_is_a_noop():
    """When disabled, nothing is recorded and collect returns empty."""
    previous = settings.PHASE_TIMING_ENABLED
    settings.PHASE_TIMING_ENABLED = False
    try:
        with phase_timer.timed_phase("preprocess_ms"):
            pass
        phase_timer.record_attr("cache_hit", True)
        assert phase_timer.collect_phases() == {}
    finally:
        settings.PHASE_TIMING_ENABLED = previous


def test_start_root_phases_seeds_pre_handler(timing_on):
    """A prior entry stamp yields pre_handler_ms on the fresh accumulator."""
    phase_timer.mark_request_entry()
    phase_timer.start_root_phases()
    assert "pre_handler_ms" in phase_timer.collect_phases()


@pytest.mark.asyncio
async def test_phases_merge_onto_root_span(timing_on):
    """A root traced_span merges collected phases into its attributes."""
    from trace import request_span

    captured = {}

    def _capture(span, span_name, attributes, **kwargs):
        captured.update(attributes)

    # finalize_span emits the OTel log line; intercept to read the merged attrs.
    original = request_span.finalize_span
    request_span.finalize_span = _capture
    try:
        with request_span.traced_span("request", root=True, classify_status=True):
            with phase_timer.timed_phase("postprocess_ms"):
                pass
    finally:
        request_span.finalize_span = original

    assert "postprocess_ms" in captured
    assert "total_time_ms" in captured
