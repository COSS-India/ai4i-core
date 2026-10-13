"""The scheduled Usage Viewer report (AI4IDS-3278).

Triggered once a day — by the pyjob `usage_report` CronJob, through
POST /internal/usage-report/run — and idempotent, so the schedule only has to
say "daily"; the frequency lives in configuration:

1. The due period is the latest complete period of the configured frequency
   (weekly / fortnightly / monthly), unless an already-sent period covers any
   of its days. So a frequency change takes effect from the next period of
   the new frequency, without reporting a day twice.
2. Each active Usage Viewer gets it once: SENT recipients are skipped; a
   FAILED one is retried on the next run, up to USAGE_REPORT_MAX_ATTEMPTS.
3. If any figure can't be collected, nothing is sent: a NOT_READY row is
   logged and the next run tries again.

Every attempt is logged in usage_report_send_log (period, recipient,
timestamp, status, error). Runs hold a Postgres advisory lock, so an
overlapping run (a delayed CronJob, a manual run) sends nothing twice.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Optional

from app.services.usage_report.mailer import Sender, deliver, send_report_mime
from app.services.usage_report.period import ReportPeriod, check_frequency
from app.services.usage_report.recipients import Recipient
from app.services.usage_report.send_log import SENT, SendLog

logger = logging.getLogger(__name__)

# RunResult.status values
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


async def due_period(log: SendLog, frequency: str, now: datetime, anchor: date) -> Optional[ReportPeriod]:
    """The latest complete period, or None if a different sent period already
    covers any of its days (e.g. the month that was reported just before a
    switch to weekly)."""
    period = ReportPeriod.latest_complete(frequency, now, anchor)
    last_day = await log.last_reported_day(excluding=period)
    if last_day is not None and period.first_day <= last_day:
        return None
    return period


async def run_scheduled(
    *,
    frequency: str,
    log: SendLog,
    collector,
    viewers: Callable[[], "object"],
    email_cfg,
    max_attempts: int,
    anchor: date,
    now: Optional[datetime] = None,
    render_pdf: Optional[Callable] = None,
    send: Sender = send_report_mime,
) -> RunResult:
    """One scheduled run. ``viewers`` is an async callable returning the
    active Usage Viewers; ``collector`` has UsageReportCollector.collect."""
    from app.services.usage_report.pdf import render_report_pdf

    frequency = check_frequency(frequency)
    now = now or datetime.now(timezone.utc)
    period = await due_period(log, frequency, now, anchor)
    if period is None:
        return RunResult(NOTHING_DUE, frequency, detail="already covered by a sent period")

    recipients: list[Recipient] = await viewers()
    if not recipients:
        logger.error("usage report %s: no active Usage Viewer has an email address", period.key)
        return RunResult(NO_RECIPIENTS, frequency, period.key)

    states = await log.recipient_states(period)
    pending, exhausted = [], []
    for r in recipients:
        state = states.get(r.user_id)
        if state is None:
            pending.append(r)
        elif state.status != SENT:
            (pending if state.attempts < max_attempts else exhausted).append(r)
    for r in exhausted:
        logger.error("usage report %s: gave up on Usage Viewer %s after %d attempts",
                     period.key, r.user_id, max_attempts)
    if not pending:
        return RunResult(NOTHING_DUE, frequency, period.key, detail="sent to every Usage Viewer")

    try:
        data = await collector.collect(period, now=now)
    except ValueError as exc:  # e.g. older than Prometheus retention
        await log.record_not_ready(period, str(exc))
        logger.error("usage report %s not ready: %s", period.key, exc)
        return RunResult(NOT_READY, frequency, period.key, detail=str(exc))
    if data.failed:
        reason = "figures failed to load: " + ", ".join(data.failed)
        await log.record_not_ready(period, reason)
        logger.error("usage report %s not ready, nothing sent: %s", period.key, reason)
        return RunResult(NOT_READY, frequency, period.key, detail=reason)

    pdf = (render_pdf or render_report_pdf)(data)
    result = RunResult(DONE, frequency, period.key)
    for r in pending:
        # One at a time, logged and committed after each, so a crash mid-run
        # can't make the next run resend to someone already sent to.
        _, failed = await deliver(data, pdf, [r.email], email_cfg, send=send)
        error = failed.get(r.email)
        await log.record(period, r.user_id, error)
        (result.failed if error else result.sent).append(r.user_id)
    logger.info("usage report %s (%s): sent %d, failed %d, skipped %d already sent",
                period.key, frequency, len(result.sent), len(result.failed),
                len(recipients) - len(pending) - len(exhausted))
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
    from app.core.database import get_auth_session_factory, get_engine, get_primary_session_factory
    from app.repositories.model_management.model_repository import ModelRepository
    from app.repositories.model_management.service_repository import ServiceRepository
    from app.services.metering_service import MeteringService
    from app.services.usage_report.collector import UsageReportCollector
    from app.services.usage_report.mailer import email_settings
    from app.services.usage_report.recipients import usage_viewers
    from app.services.usage_report.send_log import report_lock
    from app.utils.prometheus_client import PrometheusClient

    frequency = check_frequency(frequency or settings.usage_report_frequency)
    if not settings.prometheus_url:
        raise RuntimeError("PROMETHEUS_URL is not set; request figures cannot be collected")
    auth_factory = get_auth_session_factory()
    if auth_factory is None:
        raise RuntimeError("AUTH_DB_NAME is not set; institutions, budgets and recipients live in the auth DB")

    async with report_lock(get_engine()) as acquired:
        if not acquired:
            logger.warning("usage report: another run is in progress; skipping")
            return RunResult(BUSY, frequency)
        prometheus = PrometheusClient(settings.prometheus_url, http_client, timeout=settings.prometheus_timeout)
        async with get_primary_session_factory()() as core_db, auth_factory() as auth_db, \
                get_primary_session_factory()() as log_db:
            metering = MeteringService(prometheus, auth_db, ServiceRepository(core_db), ModelRepository(core_db))
            return await run_scheduled(
                frequency=frequency,
                log=SendLog(log_db),
                collector=UsageReportCollector(metering, auth_db, core_db),
                viewers=lambda: usage_viewers(auth_db, pii_crypto.decrypt_email),
                email_cfg=email_settings(),
                max_attempts=settings.usage_report_max_attempts,
                anchor=settings.usage_report_fortnight_anchor,
                now=now,
            )
