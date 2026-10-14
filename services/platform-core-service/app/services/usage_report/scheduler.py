"""The scheduled Usage Viewer report (AI4IDS-3278).

Triggered by the pyjob `usage_report` CronJob through
POST /internal/usage-report/run. DevOps schedules it ONCE PER PERIOD of the
configured frequency (weekly: Mondays; monthly: the 1st), because each run:

1. Picks the latest complete period of the frequency (``monthly`` or any
   duration — 1d, 7d, 14d …; under a day only where USAGE_REPORT_ALLOW_SUBDAILY
   is on, for testing).
2. If any figure can't be collected, sends nothing (status not_ready).
3. Otherwise emails it to every active Usage Viewer, one email each, and logs
   every send (period, recipient, status) and a run summary in the app logs.

There is no send log or retry in this release: a run doesn't know what
earlier runs sent, so running it more than once per period sends the report
again. Runs hold a Postgres advisory lock, so two overlapping runs don't send
at the same time.

Next release — retry failed recipients and log sends in usage_report_send_log:
the code is kept below, commented out (due_period, the send-log steps in
run_scheduled), together with app/services/usage_report/send_log.py and
app/models/usage_report/send_log.py. Re-enabling it lets the CronJob run
daily: each period is then sent once and failures are retried.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Optional

from app.services.usage_report.mailer import Sender, deliver, send_report_mime
from app.services.usage_report.period import ANCHOR, DEFAULT_FREQUENCY, Frequency, ReportPeriod
from app.services.usage_report.recipients import Recipient

# Next release (retry + send log):
# from app.services.usage_report.send_log import SENT, SendLog

logger = logging.getLogger(__name__)

# RunResult.status values (NOTHING_DUE is only returned once the send log is back)
DONE, NOTHING_DUE, NOT_READY, NO_RECIPIENTS, BUSY = "done", "nothing_due", "not_ready", "no_recipients", "busy"


@dataclass
class RunResult:
    status: str
    frequency: str
    period: Optional[str] = None
    sent: list[str] = field(default_factory=list)      # user ids
    failed: list[str] = field(default_factory=list)    # user ids
    detail: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "status": self.status, "frequency": self.frequency, "period": self.period,
            "sent": len(self.sent), "failed": len(self.failed), "detail": self.detail,
        }


# Next release (retry + send log):
# async def due_period(log: SendLog, frequency: str, now: datetime, anchor: date) -> Optional[ReportPeriod]:
#     """The latest complete period, or None if a different sent period already
#     covers any of its time (e.g. the month that was reported just before a
#     switch to weekly)."""
#     period = ReportPeriod.latest_complete(frequency, now, anchor)
#     last_end = await log.last_reported_end(excluding=period)
#     if last_end is not None and period.start < last_end:
#         return None
#     return period


async def run_scheduled(
    *,
    frequency: str,
    collector,
    viewers: Callable[[], "object"],
    email_cfg,
    anchor: date,
    now: Optional[datetime] = None,
    render_pdf: Optional[Callable] = None,
    send: Sender = send_report_mime,
    allow_subdaily: bool = False,
    # Next release (retry + send log):
    # log: SendLog,
    # max_attempts: int,
) -> RunResult:
    """One scheduled run. ``viewers`` is an async callable returning the
    active Usage Viewers; ``collector`` has UsageReportCollector.collect."""
    from app.services.usage_report.pdf import render_report_pdf

    freq = Frequency.parse(frequency)
    if freq.is_subdaily and not allow_subdaily:
        raise ValueError(f"{frequency!r} is under a day: test environments only; set USAGE_REPORT_ALLOW_SUBDAILY=true there")
    frequency = freq.name
    now = now or datetime.now(timezone.utc)
    period = ReportPeriod.latest_complete(frequency, now, anchor)
    # Next release (retry + send log): skip a period that was already sent.
    # period = await due_period(log, frequency, now, anchor)
    # if period is None:
    #     return RunResult(NOTHING_DUE, frequency, detail="already covered by a sent period")

    recipients: list[Recipient] = await viewers()
    if not recipients:
        logger.error("usage report %s: no active Usage Viewer has an email address", period.key)
        return RunResult(NO_RECIPIENTS, frequency, period.key)

    pending = recipients
    # Next release (retry + send log): only Usage Viewers not yet sent to, and
    # failed ones until they reach max_attempts.
    # states = await log.recipient_states(period)
    # pending, exhausted = [], []
    # for r in recipients:
    #     state = states.get(r.user_id)
    #     if state is None:
    #         pending.append(r)
    #     elif state.status != SENT:
    #         (pending if state.attempts < max_attempts else exhausted).append(r)
    # for r in exhausted:
    #     logger.error("usage report %s: gave up on Usage Viewer %s after %d attempts",
    #                  period.key, r.user_id, max_attempts)
    # if not pending:
    #     return RunResult(NOTHING_DUE, frequency, period.key, detail="sent to every Usage Viewer")

    try:
        data = await collector.collect(period, now=now)
    except ValueError as exc:  # e.g. older than Prometheus retention
        # Next release (retry + send log): await log.record_not_ready(period, str(exc))
        logger.error("usage report %s not ready, nothing sent: %s", period.key, exc)
        return RunResult(NOT_READY, frequency, period.key, detail=str(exc))
    if data.failed:
        reason = "figures failed to load: " + ", ".join(data.failed)
        # Next release (retry + send log): await log.record_not_ready(period, reason)
        logger.error("usage report %s not ready, nothing sent: %s", period.key, reason)
        return RunResult(NOT_READY, frequency, period.key, detail=reason)

    pdf = (render_pdf or render_report_pdf)(data)
    result = RunResult(DONE, frequency, period.key)
    user_ids = {r.email: r.user_id for r in pending}

    def record(email: str, error: Optional[str]) -> None:
        # Called right after each send, so the log shows who got it even if the
        # run stops part-way. Next release (retry + send log): log.record(...)
        user_id = user_ids[email]
        logger.log(logging.ERROR if error else logging.INFO,
                   "usage report send | period=%s frequency=%s recipient=%s status=%s%s",
                   period.key, frequency, user_id, "FAILED" if error else "SENT",
                   f" error={error}" if error else "")
        (result.failed if error else result.sent).append(user_id)

    await deliver(data, pdf, list(user_ids), email_cfg, send=send, on_result=record)
    logger.info("usage report %s (%s): sent %d, failed %d", period.key, frequency, len(result.sent), len(result.failed))
    return result


async def run_scheduled_report(
    frequency: Optional[str],
    http_client,
    now: Optional[datetime] = None,
) -> RunResult:
    """run_scheduled() wired to the service's DBs, Prometheus and SMTP. Used
    by POST /internal/usage-report/run and `send_usage_report --scheduled`."""
    from ai4i_core import pii_crypto

    from app.core.config import settings
    from app.core.database import get_engine
    from app.services.usage_report.mailer import email_settings
    from app.services.usage_report.recipients import usage_viewers
    from app.services.usage_report.send_log import report_lock
    from app.services.usage_report.sources import report_sources

    frequency = Frequency.parse(frequency or DEFAULT_FREQUENCY).name
    async with report_lock(get_engine()) as acquired:
        if not acquired:
            logger.warning("usage report: another run is in progress; skipping")
            return RunResult(BUSY, frequency)
        # Next release (retry + send log): also open a session for the log:
        #     get_primary_session_factory()() as log_db
        async with report_sources(http_client) as src:
            return await run_scheduled(
                frequency=frequency,
                collector=src.collector,
                viewers=lambda: usage_viewers(src.auth_db, pii_crypto.decrypt_email),
                email_cfg=email_settings(),
                anchor=ANCHOR,
                now=now,
                allow_subdaily=settings.usage_report_allow_subdaily,
                # Next release (retry + send log):
                # log=SendLog(log_db),
                # max_attempts=settings.usage_report_max_attempts,
            )
