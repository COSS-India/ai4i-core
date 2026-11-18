"""daily_usage_consolidation.run(): the usage consolidation and the key expiry
reminder step are independent, and a failure in either fails the job.
No database needed."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jobs import daily_usage_consolidation as job  # noqa: E402


@pytest.fixture
def steps(monkeypatch):
    calls = []

    async def consolidate(today):
        calls.append("consolidate")

    async def run_key_expiry_alerts():
        calls.append("alerts")

    monkeypatch.setattr(job, "consolidate", consolidate)
    monkeypatch.setattr(job, "run_key_expiry_alerts", run_key_expiry_alerts)
    return calls


@pytest.mark.asyncio
async def test_both_steps_run(steps):
    await job.run()
    assert steps == ["consolidate", "alerts"]


@pytest.mark.asyncio
async def test_a_failed_consolidation_still_sends_reminders_and_fails_the_job(steps, monkeypatch):
    async def broken(today):
        raise RuntimeError("rollup down")

    monkeypatch.setattr(job, "consolidate", broken)
    with pytest.raises(RuntimeError, match="usage consolidation"):
        await job.run()
    assert steps == ["alerts"]


@pytest.mark.asyncio
async def test_failed_reminders_fail_the_job_after_consolidation(steps, monkeypatch):
    async def broken():
        raise RuntimeError("kafka down")

    monkeypatch.setattr(job, "run_key_expiry_alerts", broken)
    with pytest.raises(RuntimeError, match="key expiry reminders"):
        await job.run()
    assert steps == ["consolidate"]
