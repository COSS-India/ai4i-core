"""Scheduled Usage Viewer report (AI4IDS-3278).

Run by k8s once a day (schedule set by DevOps; after daily_usage_consolidation,
in business hours). Triggers POST /internal/usage-report/run on platform-core,
which does the work: picks the due period for USAGE_REPORT_FREQUENCY, emails
the report and PDF to every Usage Viewer who hasn't had it, retries earlier
failures, and logs each send in usage_report_send_log. Running daily is what
makes retries and frequency changes work without touching the schedule; a
run with nothing due sends nothing.

Handled outcomes — nothing due, not ready, some recipients failed — exit 0:
they are logged by platform-core and retried by the next daily run. A k8s
retry within minutes would only use up the per-recipient attempts. The job
fails (exit 1) only when platform-core can't be reached or errors.
"""
from __future__ import annotations

from ai4i_core.logging import get_logger

from bootstrap.config import get_settings
from bootstrap.platform_core import call_internal

logger = get_logger(__name__)


async def run() -> None:
    frequency = get_settings().USAGE_REPORT_FREQUENCY
    result = await call_internal("usage-report/run", {"frequency": frequency} if frequency else {})
    log = logger.warning if result.get("status") in ("not_ready", "no_recipients") or result.get("failed") else logger.info
    log(
        "Usage report run | status=%s frequency=%s period=%s sent=%s failed=%s detail=%s",
        result.get("status"), result.get("frequency"), result.get("period"),
        result.get("sent"), result.get("failed"), result.get("detail"),
    )
