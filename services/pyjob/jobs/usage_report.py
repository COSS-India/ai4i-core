"""Scheduled Usage Viewer report (AI4IDS-3278).

Run by k8s ONCE PER PERIOD of USAGE_REPORT_FREQUENCY (schedule set by DevOps,
in business hours, after daily_usage_consolidation): weekly → Mondays,
monthly → the 1st. Triggers POST /internal/usage-report/run on platform-core,
which emails the latest complete period's report and PDF to every Usage
Viewer and logs each send. There is no send log or retry in this release, so
every run sends again: the schedule must match the frequency, and a changed
frequency needs the schedule changed with it.

The job fails (exit 1) when the report wasn't sent to everyone — not ready,
no Usage Viewers, some recipients failed, any status it doesn't know — or
platform-core errors, so the CronJob shows it. Before re-running a failed
job, check the logs: a re-run sends to everyone again, including those who
already got it.

"busy" (another run holds platform-core's lock and is sending this period)
exits 0 with a warning, like the other jobs' lock skips: that run reports its
own outcome, and failing here would invite a re-run that sends twice.
"""
from __future__ import annotations

from ai4i_core.logging import get_logger

from bootstrap.config import get_settings
from bootstrap.platform_core import call_internal

logger = get_logger(__name__)

# platform-core's RunResult statuses (app.services.usage_report.scheduler).
# nothing_due only comes back once the send log returns.
DONE, NOTHING_DUE, BUSY = "done", "nothing_due", "busy"


async def run() -> None:
    frequency = get_settings().USAGE_REPORT_FREQUENCY
    result = await call_internal("usage-report/run", {"frequency": frequency} if frequency else {})
    status = result.get("status")
    if status == BUSY:
        log, complete = logger.warning, True
    else:
        complete = status == NOTHING_DUE or (status == DONE and not result.get("failed"))
        log = logger.info if complete else logger.error
    log(
        "Usage report run%s | status=%s frequency=%s period=%s sent=%s failed=%s detail=%s",
        " SKIPPED: another run is in progress and sends this period; do not re-run" if status == BUSY else "",
        status, result.get("frequency"), result.get("period"),
        result.get("sent"), result.get("failed"), result.get("detail"),
    )
    if not complete:
        raise RuntimeError(f"usage report not sent to every Usage Viewer: {result}")
