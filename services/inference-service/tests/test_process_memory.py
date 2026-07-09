"""Unit tests for per-request process memory logging."""

from unittest.mock import patch

import pytest

from config import settings
from process_memory import (
    ProcessMemorySnapshot,
    collect_request_memory,
    format_memory_summary,
    start_request_memory,
)


@pytest.fixture
def memory_on():
    previous = settings.MEMORY_LOG_ENABLED
    settings.MEMORY_LOG_ENABLED = True
    yield
    settings.MEMORY_LOG_ENABLED = previous


def test_format_memory_summary_includes_before_after_delta():
    line = format_memory_summary({
        "memory_rss_before_mb": 120.5,
        "memory_rss_after_mb": 125.75,
        "memory_rss_delta_mb": 5.25,
    })
    assert line == "MEMORY rss_before=120.5MB rss_after=125.75MB rss_delta=5.25MB"


def test_format_memory_summary_after_only():
    line = format_memory_summary({"memory_rss_after_mb": 90.0})
    assert line == "MEMORY rss_after=90.0MB"


def test_collect_request_memory_disabled():
    previous = settings.MEMORY_LOG_ENABLED
    settings.MEMORY_LOG_ENABLED = False
    try:
        start_request_memory()
        assert collect_request_memory() == {}
    finally:
        settings.MEMORY_LOG_ENABLED = previous


def test_collect_request_memory_before_after(memory_on):
    before = ProcessMemorySnapshot(rss_bytes=100 * 1024 * 1024, vms_bytes=200 * 1024 * 1024)
    after = ProcessMemorySnapshot(rss_bytes=110 * 1024 * 1024, vms_bytes=210 * 1024 * 1024)

    with patch("process_memory.get_process_memory_snapshot", side_effect=[before, after]):
        start_request_memory()
        result = collect_request_memory()

    assert result["memory_rss_before_mb"] == 100.0
    assert result["memory_rss_after_mb"] == 110.0
    assert result["memory_rss_delta_mb"] == 10.0
    assert result["memory_vms_before_mb"] == 200.0
    assert result["memory_vms_after_mb"] == 210.0
    assert result["memory_vms_delta_mb"] == 10.0
