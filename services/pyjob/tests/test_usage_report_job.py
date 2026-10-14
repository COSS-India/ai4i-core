"""jobs/usage_report: how platform-core's run outcome maps to the job's exit
(raise → exit 1) and log level."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jobs import usage_report


@pytest.fixture
def platform_core(monkeypatch):
    """Stubs the internal call; set .return_value to platform-core's reply."""
    call = AsyncMock()
    monkeypatch.setattr(usage_report, "call_internal", call)
    monkeypatch.setattr(usage_report, "get_settings", lambda: SimpleNamespace(USAGE_REPORT_FREQUENCY="monthly"))
    return call


def _reply(status, sent=0, failed=0):
    return {"status": status, "frequency": "monthly", "period": "2026-09",
            "sent": sent, "failed": failed, "detail": None}


def _job_logs(caplog):
    return [r for r in caplog.records if r.name == usage_report.__name__]


@pytest.mark.asyncio
async def test_busy_is_a_warning_not_a_green_info_line(platform_core, caplog):
    # A second run while the first holds platform-core's lock: nothing sent by
    # this run. It must not read as a normal run in the logs, nor fail (a
    # failed CronJob gets re-run, and that run would send everyone a second copy).
    platform_core.return_value = {"status": "busy", "frequency": "monthly", "period": None,
                                  "sent": 0, "failed": 0, "detail": None}
    with caplog.at_level(logging.INFO):
        await usage_report.run()
    [record] = _job_logs(caplog)
    assert record.levelno == logging.WARNING
    assert "SKIPPED" in record.getMessage() and "do not re-run" in record.getMessage()


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [_reply("done", sent=3), _reply("nothing_due")])
async def test_complete_runs_succeed_at_info(platform_core, caplog, reply):
    platform_core.return_value = reply
    with caplog.at_level(logging.INFO):
        await usage_report.run()
    [record] = _job_logs(caplog)
    assert record.levelno == logging.INFO


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [
    _reply("done", sent=2, failed=1),
    _reply("not_ready"),
    _reply("no_recipients"),
    _reply("something_new"),   # a status this job doesn't know is not a success
    {},                        # an empty 2xx body is not a success either
])
async def test_incomplete_or_unknown_outcomes_fail_the_job(platform_core, caplog, reply):
    platform_core.return_value = reply
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match="not sent to every Usage Viewer"):
        await usage_report.run()
    [record] = _job_logs(caplog)
    assert record.levelno == logging.ERROR


@pytest.mark.asyncio
async def test_sends_the_jobs_frequency(platform_core):
    platform_core.return_value = _reply("done", sent=1)
    await usage_report.run()
    platform_core.assert_awaited_once_with("usage-report/run", {"frequency": "monthly"})
