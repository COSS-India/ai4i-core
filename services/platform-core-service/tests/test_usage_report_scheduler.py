"""Scheduled Usage Viewer report (AI4IDS-3278): periods, the due-period rule,
once-per-recipient delivery, retries, not-ready handling, the send log's SQL
and the run lock."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.usage_report.send_log import UsageReportSendLog
from app.services.usage_report.period import FORTNIGHTLY, MONTHLY, WEEKLY, ReportPeriod, check_frequency
from app.services.usage_report.recipients import Recipient
from app.services.usage_report.scheduler import (
    DONE, NO_RECIPIENTS, NOT_READY, NOTHING_DUE, due_period, run_scheduled,
)
from app.services.usage_report.send_log import FAILED, SENT, RecipientState, SendLog, report_lock
from tests.test_usage_report import _email_cfg, _full_data

UTC = timezone.utc
ANCHOR = date(2026, 1, 5)


def ist(y, m, d, hh=9, mm=0) -> datetime:
    """An IST wall-clock time, as UTC."""
    return datetime(y, m, d, hh, mm, tzinfo=UTC) - timedelta(hours=5, minutes=30)


# ── periods ──────────────────────────────────────────────────────────────────


class TestPeriods:
    def test_weekly_is_monday_to_sunday(self):
        p = ReportPeriod.containing(WEEKLY, date(2026, 10, 14))  # a Wednesday
        assert (p.first_day, p.last_day) == (date(2026, 10, 12), date(2026, 10, 18))

    @pytest.mark.parametrize("now,expected", [
        (ist(2026, 10, 12, 0, 30), (date(2026, 10, 5), date(2026, 10, 11))),   # Monday just after midnight IST
        (ist(2026, 10, 18, 23), (date(2026, 10, 5), date(2026, 10, 11))),      # Sunday: current week not done
        (ist(2026, 10, 19), (date(2026, 10, 12), date(2026, 10, 18))),
    ])
    def test_latest_complete_week(self, now, expected):
        p = ReportPeriod.latest_complete(WEEKLY, now, ANCHOR)
        assert (p.first_day, p.last_day) == expected

    def test_monday_0100_ist_is_still_sunday_in_utc_but_the_week_is_complete(self):
        # 19:30 UTC Sunday = 01:00 IST Monday: reading the day in UTC would wait a day.
        p = ReportPeriod.latest_complete(WEEKLY, datetime(2026, 10, 11, 19, 30, tzinfo=UTC), ANCHOR)
        assert p.last_day == date(2026, 10, 11)

    def test_fortnights_are_14_day_blocks_from_the_anchor(self):
        p = ReportPeriod.containing(FORTNIGHTLY, date(2026, 10, 14), ANCHOR)
        assert (p.first_day, p.last_day) == (date(2026, 10, 12), date(2026, 10, 25))
        before = ReportPeriod.containing(FORTNIGHTLY, date(2025, 12, 30), ANCHOR)  # before the anchor
        assert (before.first_day, before.last_day) == (date(2025, 12, 22), date(2026, 1, 4))
        assert ReportPeriod.latest_complete(FORTNIGHTLY, ist(2026, 10, 13), ANCHOR).first_day == date(2026, 9, 28)

    @pytest.mark.parametrize("now,month", [(ist(2026, 10, 1, 0, 5), 9), (ist(2026, 9, 30, 23), 8)])
    def test_latest_complete_month(self, now, month):
        assert ReportPeriod.latest_complete(MONTHLY, now, ANCHOR) == ReportPeriod.month(2026, month)

    def test_wording(self):
        week = ReportPeriod(WEEKLY, date(2026, 9, 28), date(2026, 10, 4))
        assert week.label == "28 Sep – 4 Oct 2026" and week.short_label == "28 Sep–4 Oct"
        assert week.title == "Weekly" and week.in_phrase == "this week" and week.vs_phrase == "vs previous week"
        assert week.key == "2026-09-28_2026-10-04"
        assert week.previous() == ReportPeriod(WEEKLY, date(2026, 9, 21), date(2026, 9, 27))
        new_year = ReportPeriod(FORTNIGHTLY, date(2025, 12, 22), date(2026, 1, 4))
        assert new_year.label == "22 Dec 2025 – 4 Jan 2026" and new_year.vs_phrase == "vs previous fortnight"
        month = ReportPeriod.month(2026, 9)
        assert (month.label, month.title, month.in_phrase, month.vs_phrase, month.key) == (
            "September 2026", "Monthly", "in September", "vs August", "2026-09")

    def test_frequency_is_validated(self):
        assert check_frequency(" Weekly ") == WEEKLY
        with pytest.raises(ValueError):
            check_frequency("daily")


# ── scheduler (in-memory send log) ───────────────────────────────────────────


class FakeLog:
    """In-memory SendLog with the same semantics as the SQL one."""

    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.not_ready: list[tuple] = []

    @staticmethod
    def _key(p: ReportPeriod):
        return (p.frequency, p.first_day, p.last_day)

    async def last_reported_day(self, excluding):
        days = [k[2] for (k, _), r in self.rows.items() if r["status"] == SENT and k != self._key(excluding)]
        return max(days, default=None)

    async def recipient_states(self, period):
        return {uid: RecipientState(r["status"], r["attempts"])
                for (k, uid), r in self.rows.items() if k == self._key(period)}

    async def record(self, period, user_id, error):
        row = self.rows.setdefault((self._key(period), user_id), {"attempts": 0})
        row.update(status=SENT if error is None else FAILED, error=error, attempts=row["attempts"] + 1)

    async def record_not_ready(self, period, reason):
        self.not_ready.append((self._key(period), reason))

    def status(self, period, uid):
        return self.rows.get((self._key(period), uid), {}).get("status")


class FakeCollector:
    def __init__(self, failed=None, error=None):
        self.failed, self.error, self.calls = failed or [], error, []

    async def collect(self, period, now=None):
        self.calls.append(period)
        if self.error:
            raise self.error
        data = _full_data()
        return replace(data, period=period, failed=list(self.failed))


VIEWERS = [Recipient("u1", "a@x.gov.in"), Recipient("u2", "b@x.gov.in")]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr("app.services.usage_report.mailer.settings.portal_url", "https://portal.gov.in")
    monkeypatch.setattr("app.services.usage_report.mailer.settings.usage_report_sender_name", None)
    state = SimpleNamespace(log=FakeLog(), collector=FakeCollector(), viewers=list(VIEWERS),
                            sent_to=[], failing=set())

    async def send(mime, cfg):
        if mime["To"] in state.failing:
            raise RuntimeError("relay refused")
        state.sent_to.append((mime["To"], mime["Subject"]))

    async def run(frequency=MONTHLY, now=ist(2026, 10, 13), max_attempts=3):
        async def viewers():
            return state.viewers
        return await run_scheduled(
            frequency=frequency, log=state.log, collector=state.collector, viewers=viewers,
            email_cfg=_email_cfg(), max_attempts=max_attempts, anchor=ANCHOR, now=now,
            render_pdf=lambda data: b"%PDF-1.4", send=send,
        )

    state.run = run
    return state


SEP = ReportPeriod.month(2026, 9)


class TestScheduledRun:
    @pytest.mark.asyncio
    async def test_sends_the_due_period_to_every_usage_viewer_and_logs_it(self, env):
        result = await env.run()
        assert (result.status, result.period, result.sent, result.failed) == (DONE, "2026-09", ["u1", "u2"], [])
        assert [to for to, _ in env.sent_to] == ["a@x.gov.in", "b@x.gov.in"]
        assert env.sent_to[0][1] == "AI Switch – Monthly programme report – September 2026"
        assert env.log.status(SEP, "u1") == SENT and env.log.status(SEP, "u2") == SENT

    @pytest.mark.asyncio
    async def test_running_again_sends_nothing_twice(self, env):
        # The daily CronJob runs every day of October: September goes out once.
        await env.run(now=ist(2026, 10, 1))
        for day in range(2, 31):
            result = await env.run(now=ist(2026, 10, day))
            assert result.status == NOTHING_DUE
        assert len(env.sent_to) == 2
        assert len(env.collector.calls) == 1  # no figures collected once everyone has it

    @pytest.mark.asyncio
    async def test_a_failed_recipient_is_retried_on_the_next_run_only(self, env):
        env.failing = {"b@x.gov.in"}
        first = await env.run(now=ist(2026, 10, 1))
        assert (first.sent, first.failed) == (["u1"], ["u2"])
        assert env.log.rows[(("monthly", SEP.first_day, SEP.last_day), "u2")]["error"].startswith("relay refused")
        env.failing = set()
        second = await env.run(now=ist(2026, 10, 2))
        assert (second.sent, second.failed) == (["u2"], [])
        assert [to for to, _ in env.sent_to] == ["a@x.gov.in", "b@x.gov.in"]  # a@ not sent twice
        assert env.log.rows[(("monthly", SEP.first_day, SEP.last_day), "u2")]["attempts"] == 2

    @pytest.mark.asyncio
    async def test_gives_up_after_max_attempts(self, env):
        env.failing = {"b@x.gov.in"}
        for day in (1, 2, 3):
            await env.run(now=ist(2026, 10, day), max_attempts=3)
        result = await env.run(now=ist(2026, 10, 4), max_attempts=3)
        assert result.status == NOTHING_DUE
        assert env.log.rows[(("monthly", SEP.first_day, SEP.last_day), "u2")] == {
            "attempts": 3, "status": FAILED, "error": "relay refused (RuntimeError)"}

    @pytest.mark.asyncio
    async def test_report_not_ready_sends_nothing_and_retries_next_run(self, env):
        env.collector.failed = ["total_requests"]
        result = await env.run(now=ist(2026, 10, 1))
        assert result.status == NOT_READY and env.sent_to == []
        assert env.log.not_ready == [(("monthly", SEP.first_day, SEP.last_day), "figures failed to load: total_requests")]
        env.collector.failed = []
        assert (await env.run(now=ist(2026, 10, 2))).status == DONE
        assert len(env.sent_to) == 2

    @pytest.mark.asyncio
    async def test_collector_rejecting_the_period_is_not_ready(self, env):
        env.collector.error = ValueError("September 2026 starts before the oldest retained metering data")
        result = await env.run()
        assert result.status == NOT_READY and "oldest retained" in result.detail and env.sent_to == []

    @pytest.mark.asyncio
    async def test_a_new_usage_viewer_gets_the_current_period_without_resending_others(self, env):
        await env.run(now=ist(2026, 10, 1))
        env.viewers = VIEWERS + [Recipient("u3", "c@x.gov.in")]
        result = await env.run(now=ist(2026, 10, 2))
        assert result.sent == ["u3"] and [to for to, _ in env.sent_to][-1] == "c@x.gov.in"
        assert len(env.sent_to) == 3

    @pytest.mark.asyncio
    async def test_no_usage_viewers(self, env):
        env.viewers = []
        assert (await env.run()).status == NO_RECIPIENTS

    @pytest.mark.asyncio
    async def test_bad_frequency_is_rejected(self, env):
        with pytest.raises(ValueError):
            await env.run(frequency="daily")


class TestFrequencyChange:
    """AC: "If the frequency is changed, the change takes effect from the next
    reporting period" — and no day is reported twice."""

    @pytest.mark.asyncio
    async def test_monthly_to_weekly_starts_with_the_first_whole_week_after_the_month(self, env):
        await env.run(MONTHLY, now=ist(2026, 10, 1))                 # September sent
        # Switched to weekly on Tue 6 Oct: week 28 Sep–4 Oct overlaps September.
        assert (await env.run(WEEKLY, now=ist(2026, 10, 6))).status == NOTHING_DUE
        result = await env.run(WEEKLY, now=ist(2026, 10, 12))       # week 5–11 Oct: first weekly report
        assert (result.status, result.period) == (DONE, "2026-10-05_2026-10-11")
        assert env.sent_to[-1][1] == "AI Switch – Weekly programme report – 5–11 Oct 2026"

    @pytest.mark.asyncio
    async def test_weekly_to_monthly_waits_for_the_next_whole_month(self, env):
        await env.run(WEEKLY, now=ist(2026, 10, 12))                 # 5–11 Oct sent
        # Switched to monthly: October overlaps a sent week, so it is skipped...
        assert (await env.run(MONTHLY, now=ist(2026, 11, 1))).status == NOTHING_DUE
        # ...and November is the first monthly report.
        result = await env.run(MONTHLY, now=ist(2026, 12, 1))
        assert (result.status, result.period) == (DONE, "2026-11")

    @pytest.mark.asyncio
    async def test_due_period_ignores_the_period_being_delivered(self, env):
        # A partly-sent period mustn't count as "already covered" for itself.
        await env.log.record(SEP, "u1", None)
        assert await due_period(env.log, MONTHLY, ist(2026, 10, 2), ANCHOR) == SEP


# ── send log SQL and run lock (live ai4iplatform_core; skipped without one) ──


@pytest_asyncio.fixture()
async def engine():
    from tests.test_period_usage_repository import _url

    eng = create_async_engine(_url(), connect_args={"timeout": 5})
    try:
        async with eng.connect() as conn:
            await conn.scalar(text("SELECT 1"))
    except Exception as exc:
        await eng.dispose()
        pytest.skip(f"could not connect to ai4iplatform_core: {exc}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def log_session(engine):
    """A SendLog on a rolled-back transaction; creates the table inside it
    when the DB isn't migrated yet."""
    conn = await engine.connect()
    trans = await conn.begin()
    await conn.run_sync(lambda sync: UsageReportSendLog.__table__.create(sync, checkfirst=True))
    await conn.execute(text("DELETE FROM usage_report_send_log"))
    try:
        yield SendLog(AsyncSession(bind=conn, join_transaction_mode="create_savepoint"))
    finally:
        await trans.rollback()
        await conn.close()


class TestSendLogSql:
    @pytest.mark.asyncio
    async def test_record_upserts_one_row_per_recipient_and_counts_attempts(self, log_session):
        log = log_session
        await log.record(SEP, "u1", "relay refused")
        await log.record(SEP, "u1", None)
        await log.record(SEP, "u2", None)
        states = await log.recipient_states(SEP)
        assert states == {"u1": RecipientState(SENT, 2), "u2": RecipientState(SENT, 1)}

    @pytest.mark.asyncio
    async def test_last_reported_day_skips_the_excluded_period_and_failures(self, log_session):
        log = log_session
        week = ReportPeriod(WEEKLY, date(2026, 10, 5), date(2026, 10, 11))
        await log.record(SEP, "u1", None)
        await log.record(week, "u1", "boom")              # FAILED only: not "reported"
        await log.record_not_ready(week, "figures failed")
        assert await log.last_reported_day(excluding=week) == date(2026, 9, 30)
        assert await log.last_reported_day(excluding=SEP) is None


class TestRunLock:
    @pytest.mark.asyncio
    async def test_a_second_run_cannot_take_the_lock_until_the_first_releases_it(self, engine):
        async with report_lock(engine) as first:
            assert first is True
            async with report_lock(engine) as second:
                assert second is False
        async with report_lock(engine) as again:
            assert again is True


# ── POST /internal/usage-report/run ──────────────────────────────────────────


def _internal_module():
    """Loaded by file path, as tests/test_internal_service_resolution.py does."""
    import importlib.util
    import sys

    import ai4i_core.kafka  # noqa: F401  (internal.py → tier_service needs it)

    spec = importlib.util.spec_from_file_location("app.routes.internal", "app/routes/internal.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.routes.internal"] = module
    spec.loader.exec_module(module)
    return module


class TestInternalRunEndpoint:
    def test_requires_the_internal_shared_secret(self):
        internal = _internal_module()
        route = next(r for r in internal.router.routes if r.path == "/usage-report/run")
        assert route.methods == {"POST"}
        assert internal._require_internal_caller in [d.dependency for d in route.dependencies]

    @pytest.mark.asyncio
    async def test_runs_with_the_jobs_frequency_and_returns_the_outcome(self, monkeypatch):
        from app.services.usage_report import scheduler

        internal = _internal_module()
        run = AsyncMock(return_value=scheduler.RunResult(DONE, WEEKLY, "2026-10-05_2026-10-11", ["u1"], []))
        monkeypatch.setattr(scheduler, "run_scheduled_report", run)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http_client="http")))
        body = internal.UsageReportRunRequest(frequency="weekly")
        assert await internal.usage_report_run(request, body) == {
            "status": "done", "frequency": "weekly", "period": "2026-10-05_2026-10-11",
            "sent": 1, "failed": 0, "detail": None}
        run.assert_awaited_once_with("weekly", "http")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error,code", [(ValueError("bad frequency"), 422), (RuntimeError("no PROMETHEUS_URL"), 503)])
    async def test_errors_map_to_status_codes(self, monkeypatch, error, code):
        from fastapi import HTTPException

        from app.services.usage_report import scheduler

        internal = _internal_module()
        monkeypatch.setattr(scheduler, "run_scheduled_report", AsyncMock(side_effect=error))
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http_client=None)))
        with pytest.raises(HTTPException) as exc:
            await internal.usage_report_run(request, internal.UsageReportRunRequest())
        assert exc.value.status_code == code
