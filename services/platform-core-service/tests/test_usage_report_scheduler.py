"""Scheduled Usage Viewer report (AI4IDS-3278): periods, sending the latest
period to every Usage Viewer, not-ready handling, the run lock and the
internal endpoint.

The send log (usage_report_send_log) and retries are not in this release;
their tests are kept below, commented out, with the code they test."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Next release (retry + send log):
# from sqlalchemy.ext.asyncio import AsyncSession
# from app.models.usage_report.send_log import UsageReportSendLog
from app.services.usage_report.period import (
    DAILY, FORTNIGHTLY, HALF_HOURLY, HOURLY, MONTHLY, WEEKLY, ReportPeriod, check_frequency,
)
from app.services.usage_report.recipients import Recipient
from app.utils.usage_period import IST
from app.services.usage_report.scheduler import DONE, NO_RECIPIENTS, NOT_READY, run_scheduled
from app.services.usage_report.send_log import report_lock

# Next release (retry + send log):
# from app.services.usage_report.scheduler import NOTHING_DUE, due_period
# from app.services.usage_report.send_log import FAILED, SENT, RecipientState, SendLog
from tests.test_usage_report import _email_cfg, _full_data, set_branding

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
        week = ReportPeriod.days(WEEKLY, date(2026, 9, 28), date(2026, 10, 4))
        assert week.label == "28 Sep – 4 Oct 2026" and week.short_label == "28 Sep–4 Oct"
        assert week.title == "Weekly" and week.in_phrase == "this week" and week.vs_phrase == "vs previous week"
        assert week.key == "2026-09-28_2026-10-04"
        assert week.previous() == ReportPeriod.days(WEEKLY, date(2026, 9, 21), date(2026, 9, 27))
        new_year = ReportPeriod.days(FORTNIGHTLY, date(2025, 12, 22), date(2026, 1, 4))
        assert new_year.label == "22 Dec 2025 – 4 Jan 2026" and new_year.vs_phrase == "vs previous fortnight"
        month = ReportPeriod.month(2026, 9)
        assert (month.label, month.title, month.in_phrase, month.vs_phrase, month.key) == (
            "September 2026", "Monthly", "in September", "vs August", "2026-09")

    def test_frequency_is_validated(self):
        assert check_frequency(" Weekly ") == WEEKLY
        with pytest.raises(ValueError):
            check_frequency("yearly")


class TestShortPeriods:
    """daily, plus 30min / hourly for test environments."""

    def test_daily_is_yesterday_in_ist(self):
        p = ReportPeriod.latest_complete(DAILY, ist(2026, 10, 14, 0, 10), ANCHOR)
        assert (p.first_day, p.last_day, p.label, p.key) == (date(2026, 10, 13), date(2026, 10, 13), "13 Oct 2026", "2026-10-13")
        assert (p.title, p.in_phrase, p.vs_phrase, p.day_count) == ("Daily", "on 13 Oct", "vs previous day", 1)

    @pytest.mark.parametrize("now,start,end", [
        (ist(2026, 10, 14, 10, 33), (10, 0), (10, 30)),   # :33 → the 10:00–10:30 block (settled)
        (ist(2026, 10, 14, 10, 31), (9, 30), (10, 0)),    # :31 → 10:00–10:30 ended < 2 min ago
        (ist(2026, 10, 14, 0, 5), (23, 30), (0, 0)),      # just after midnight → last block of the 13th
    ])
    def test_half_hour_blocks_follow_the_ist_clock_and_settle(self, now, start, end):
        p = ReportPeriod.latest_complete(HALF_HOURLY, now, ANCHOR)
        assert (p.start.astimezone(IST).hour, p.start.astimezone(IST).minute) == start
        assert (p.end.astimezone(IST).hour, p.end.astimezone(IST).minute) == end
        assert p.end - p.start == timedelta(minutes=30)

    def test_hourly_blocks_are_ist_hours(self):
        p = ReportPeriod.latest_complete(HOURLY, ist(2026, 10, 14, 10, 5), ANCHOR)
        assert (p.label, p.short_label, p.key) == ("14 Oct 2026, 09:00–10:00 IST", "09:00–10:00", "2026-10-14T09-00_10-00")
        assert (p.title, p.vs_phrase, p.day_count) == ("Hourly", "vs previous hour", None)
        # 09:00 IST is 03:30 UTC: hours are IST hours, not UTC hours.
        assert p.start == datetime(2026, 10, 14, 3, 30, tzinfo=UTC)
        assert p.previous().end == p.start

    def test_sub_day_period_reads_usage_events_not_daily_usage(self):
        p = ReportPeriod.latest_complete(HALF_HOURLY, ist(2026, 10, 14, 10, 33), ANCHOR)
        up = p.usage_period(ist(2026, 10, 14, 10, 33))
        assert (up.start, up.end, up.uses_daily_usage) == (p.start, p.end, False)
        with pytest.raises(ValueError, match="not ended"):
            p.usage_period(ist(2026, 10, 14, 10, 15))

    def test_30_minute_title(self):
        assert ReportPeriod.latest_complete(HALF_HOURLY, ist(2026, 10, 14, 10, 33), ANCHOR).title == "30-minute"


class TestFrequencyIsConfigOnly:
    """Any duration (or monthly) from env works with no code change."""

    @pytest.mark.parametrize("value,canonical", [
        ("monthly", "monthly"), ("weekly", "7d"), ("1w", "7d"), ("7d", "7d"), ("fortnightly", "14d"),
        ("daily", "1d"), ("24h", "1d"), ("hourly", "1h"), ("60m", "1h"), ("30min", "30m"), (" 2H ", "2h"),
        ("3d", "3d"), ("90m", "90m"),
    ])
    def test_values_and_aliases_normalise(self, value, canonical):
        assert check_frequency(value) == canonical

    @pytest.mark.parametrize("bad", ["yearly", "", "7", "d", "0d", "1m", "4m", "2x", "-1d"])
    def test_invalid_or_too_short_values_are_rejected(self, bad):
        with pytest.raises(ValueError):
            check_frequency(bad)

    def test_two_hours_was_a_code_change_and_is_now_just_config(self):
        # The original failing scenario: USAGE_REPORT_FREQUENCY=2h raised ValueError.
        p = ReportPeriod.latest_complete("2h", ist(2026, 10, 14, 10, 5), ANCHOR)
        assert (p.label, p.title, p.vs_phrase, p.in_phrase) == (
            "14 Oct 2026, 08:00–10:00 IST", "2-hour", "vs previous 2 hours", "in this period")
        assert p.key == "2026-10-14T08-00_10-00" and p.day_count is None and p.is_subdaily

    def test_three_days_is_whole_ist_days_from_the_anchor(self):
        p = ReportPeriod.latest_complete("3d", ist(2026, 10, 14), ANCHOR)
        # Anchor Mon 5 Jan; 5 Oct is 273 = 91 × 3 days later, so blocks run …, 8–10, 11–13,
        # 14–16 Oct: on the 14th the latest complete one is 11–13 Oct.
        assert (p.first_day, p.last_day, p.day_count, p.whole_days) == (date(2026, 10, 11), date(2026, 10, 13), 3, True)
        assert (p.title, p.vs_phrase, p.label) == ("3-day", "vs previous 3 days", "11–13 Oct 2026")
        up = p.usage_period(ist(2026, 10, 14))
        assert up.key == "custom"  # whole days go through the dashboard's own period filter

    def test_a_duration_straddling_days_reads_events_by_timestamp(self):
        p = ReportPeriod.latest_complete("36h", ist(2026, 10, 14, 13), ANCHOR)
        assert not p.whole_days and p.day_count is None
        assert p.label == "12 Oct 12:00 – 14 Oct 2026 00:00 IST"
        assert p.usage_period(ist(2026, 10, 14, 13)).uses_daily_usage is False

    def test_aliases_and_durations_give_the_same_period(self):
        now = ist(2026, 10, 14)
        assert ReportPeriod.latest_complete("weekly", now, ANCHOR) == ReportPeriod.latest_complete("1w", now, ANCHOR)


# ── scheduler ───────────────────────────────────────────


# Next release (retry + send log):
# class FakeLog:
#     """In-memory SendLog with the same semantics as the SQL one."""
#
#     def __init__(self):
#         self.rows: dict[tuple, dict] = {}
#         self.not_ready: list[tuple] = []
#
#     @staticmethod
#     def _key(p: ReportPeriod):
#         return (p.frequency, p.start, p.end)
#
#     async def last_reported_end(self, excluding):
#         days = [k[2] for (k, _), r in self.rows.items() if r["status"] == SENT and k != self._key(excluding)]
#         return max(days, default=None)
#
#     async def recipient_states(self, period):
#         return {uid: RecipientState(r["status"], r["attempts"])
#                 for (k, uid), r in self.rows.items() if k == self._key(period)}
#
#     async def record(self, period, user_id, error):
#         row = self.rows.setdefault((self._key(period), user_id), {"attempts": 0})
#         row.update(status=SENT if error is None else FAILED, error=error, attempts=row["attempts"] + 1)
#
#     async def record_not_ready(self, period, reason):
#         self.not_ready.append((self._key(period), reason))
#
#     def status(self, period, uid):
#         return self.rows.get((self._key(period), uid), {}).get("status")


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
    set_branding(monkeypatch)
    state = SimpleNamespace(collector=FakeCollector(), viewers=list(VIEWERS), sent_to=[], failing=set())

    async def send(mime, cfg):
        if mime["To"] in state.failing:
            raise RuntimeError("relay refused")
        state.sent_to.append((mime["To"], mime["Subject"]))

    async def run(frequency=MONTHLY, now=ist(2026, 10, 13), allow_subdaily=False):
        async def viewers():
            return state.viewers
        return await run_scheduled(
            frequency=frequency, collector=state.collector, viewers=viewers,
            email_cfg=_email_cfg(), anchor=ANCHOR, now=now,
            render_pdf=lambda data: b"%PDF-1.4", send=send, allow_subdaily=allow_subdaily,
        )

    state.run = run
    return state


SEP = ReportPeriod.month(2026, 9)


class TestScheduledRun:
    @pytest.mark.asyncio
    async def test_sends_the_latest_period_to_every_usage_viewer_and_logs_each_send(self, env, caplog):
        caplog.set_level("INFO", logger="app.services.usage_report.scheduler")
        result = await env.run()
        assert (result.status, result.period, result.sent, result.failed) == (DONE, "2026-09", ["u1", "u2"], [])
        assert [to for to, _ in env.sent_to] == ["a@x.gov.in", "b@x.gov.in"]
        assert env.sent_to[0][1] == "AI Switch – Monthly programme report – September 2026"
        # AC "each send is logged with period, recipients, timestamp and status" — app logs
        # (the log record carries the timestamp) until the send-log table is back.
        sends = [r.getMessage() for r in caplog.records if r.getMessage().startswith("usage report send |")]
        assert sends == [
            "usage report send | period=2026-09 frequency=monthly recipient=u1 status=SENT",
            "usage report send | period=2026-09 frequency=monthly recipient=u2 status=SENT",
        ]

    @pytest.mark.asyncio
    async def test_a_failed_send_is_logged_and_the_others_still_go_out(self, env, caplog):
        env.failing = {"a@x.gov.in"}
        result = await env.run()
        assert (result.sent, result.failed) == (["u2"], ["u1"])
        failed = [r for r in caplog.records if "status=FAILED" in r.getMessage()]
        assert len(failed) == 1 and failed[0].levelname == "ERROR"
        assert "recipient=u1" in failed[0].getMessage() and "relay refused" in failed[0].getMessage()

    @pytest.mark.asyncio
    async def test_each_send_is_logged_as_it_happens_not_after_the_batch(self, env, caplog):
        # If the run stops part-way (pod killed), the log must already show who got it.
        caplog.set_level("INFO", logger="app.services.usage_report.scheduler")
        order = []

        async def viewers():
            return env.viewers

        async def send(mime, cfg):
            logged = [r.getMessage() for r in caplog.records if r.getMessage().startswith("usage report send |")]
            order.append(len(logged))  # sends logged BEFORE this one

        await run_scheduled(frequency=MONTHLY, collector=env.collector, viewers=viewers, email_cfg=_email_cfg(),
                            anchor=ANCHOR, now=ist(2026, 10, 13), render_pdf=lambda d: b"%PDF", send=send)
        assert order == [0, 1]  # the first send was logged before the second went out

    @pytest.mark.asyncio
    async def test_every_run_sends_again_so_the_schedule_must_match_the_frequency(self, env):
        # No send log in this release: nothing remembers what was sent. A daily
        # CronJob with a monthly frequency would mail September every day.
        await env.run(now=ist(2026, 10, 1))
        second = await env.run(now=ist(2026, 10, 2))
        assert (second.status, second.period) == (DONE, "2026-09")
        assert len(env.sent_to) == 4

    # Next release (retry + send log):
#     @pytest.mark.asyncio
#     async def test_running_again_sends_nothing_twice(self, env):
#         # The daily CronJob runs every day of October: September goes out once.
#         await env.run(now=ist(2026, 10, 1))
#         for day in range(2, 31):
#             result = await env.run(now=ist(2026, 10, day))
#             assert result.status == NOTHING_DUE
#         assert len(env.sent_to) == 2
#         assert len(env.collector.calls) == 1  # no figures collected once everyone has it
#
#     @pytest.mark.asyncio
#     async def test_a_failed_recipient_is_retried_on_the_next_run_only(self, env):
#         env.failing = {"b@x.gov.in"}
#         first = await env.run(now=ist(2026, 10, 1))
#         assert (first.sent, first.failed) == (["u1"], ["u2"])
#         assert env.log.rows[(FakeLog._key(SEP), "u2")]["error"].startswith("relay refused")
#         env.failing = set()
#         second = await env.run(now=ist(2026, 10, 2))
#         assert (second.sent, second.failed) == (["u2"], [])
#         assert [to for to, _ in env.sent_to] == ["a@x.gov.in", "b@x.gov.in"]  # a@ not sent twice
#         assert env.log.rows[(FakeLog._key(SEP), "u2")]["attempts"] == 2
#
#     @pytest.mark.asyncio
#     async def test_gives_up_after_max_attempts(self, env):
#         env.failing = {"b@x.gov.in"}
#         for day in (1, 2, 3):
#             await env.run(now=ist(2026, 10, day), max_attempts=3)
#         result = await env.run(now=ist(2026, 10, 4), max_attempts=3)
#         assert result.status == NOTHING_DUE
#         assert env.log.rows[(FakeLog._key(SEP), "u2")] == {
#             "attempts": 3, "status": FAILED, "error": "relay refused (RuntimeError)"}


    @pytest.mark.asyncio
    async def test_report_not_ready_sends_nothing(self, env):
        env.collector.failed = ["total_requests"]
        result = await env.run(now=ist(2026, 10, 1))
        assert (result.status, result.detail) == (NOT_READY, "figures failed to load: total_requests")
        assert env.sent_to == []

    @pytest.mark.asyncio
    async def test_collector_rejecting_the_period_is_not_ready(self, env):
        env.collector.error = ValueError("September 2026 starts before the oldest retained metering data")
        result = await env.run()
        assert result.status == NOT_READY and "oldest retained" in result.detail and env.sent_to == []

    # Next release (retry + send log):
#     @pytest.mark.asyncio
#     async def test_a_new_usage_viewer_gets_the_current_period_without_resending_others(self, env):
#         await env.run(now=ist(2026, 10, 1))
#         env.viewers = VIEWERS + [Recipient("u3", "c@x.gov.in")]
#         result = await env.run(now=ist(2026, 10, 2))
#         assert result.sent == ["u3"] and [to for to, _ in env.sent_to][-1] == "c@x.gov.in"
#         assert len(env.sent_to) == 3


    @pytest.mark.asyncio
    async def test_no_usage_viewers(self, env):
        env.viewers = []
        assert (await env.run()).status == NO_RECIPIENTS

    @pytest.mark.asyncio
    async def test_bad_frequency_is_rejected(self, env):
        with pytest.raises(ValueError):
            await env.run(frequency="yearly")


class TestSubDailyRuns:
    @pytest.mark.asyncio
    async def test_sub_day_frequency_is_refused_unless_allowed(self, env):
        # The guard against emailing officials every half hour from a config slip.
        with pytest.raises(ValueError, match="test environments only"):
            await env.run(HALF_HOURLY, now=ist(2026, 10, 14, 10, 33))
        assert env.sent_to == []

    @pytest.mark.asyncio
    async def test_every_30_minutes_sends_the_block_that_just_ended(self, env):
        r1 = await env.run(HALF_HOURLY, now=ist(2026, 10, 14, 10, 5), allow_subdaily=True)
        r2 = await env.run(HALF_HOURLY, now=ist(2026, 10, 14, 10, 35), allow_subdaily=True)
        assert (r1.status, r1.period) == (DONE, "2026-10-14T09-30_10-00")
        assert (r2.status, r2.period) == (DONE, "2026-10-14T10-00_10-30")
        assert len(env.sent_to) == 4  # two blocks × two viewers
        assert env.sent_to[-1][1] == "AI Switch – 30-minute programme report – 14 Oct 2026, 10:00–10:30 IST"

    # Next release (retry + send log):
#     @pytest.mark.asyncio
#     async def test_switching_from_30min_back_to_daily_waits_for_a_fresh_day(self, env):
#         await env.run(HALF_HOURLY, now=ist(2026, 10, 14, 10, 35), allow_subdaily=True)  # 14 Oct block sent
#         # 15 Oct: daily = the 14th, which overlaps that block → skipped.
#         assert (await env.run(DAILY, now=ist(2026, 10, 15))).status == NOTHING_DUE
#         result = await env.run(DAILY, now=ist(2026, 10, 16))
#         assert (result.status, result.period) == (DONE, "2026-10-15")


class TestConfigOnlyRuns:
    @pytest.mark.asyncio
    async def test_a_new_frequency_runs_end_to_end_from_config_alone(self, env):
        result = await env.run("3d", now=ist(2026, 10, 14))
        assert (result.status, result.frequency, result.period) == (DONE, "3d", "2026-10-11_2026-10-13")
        assert env.sent_to[0][1] == "AI Switch – 3-day programme report – 11–13 Oct 2026"

    @pytest.mark.asyncio
    async def test_two_hours_needs_the_test_environment_flag(self, env):
        with pytest.raises(ValueError, match="test environments only"):
            await env.run("2h", now=ist(2026, 10, 14, 10, 5))
        result = await env.run("2h", now=ist(2026, 10, 14, 10, 5), allow_subdaily=True)
        assert (result.status, result.period) == (DONE, "2026-10-14T08-00_10-00")


class TestFrequencyChangeWithoutSendLog:
    @pytest.mark.asyncio
    async def test_first_run_after_a_change_reports_the_latest_period_of_the_new_frequency(self, env):
        await env.run(MONTHLY, now=ist(2026, 10, 1))                 # September
        result = await env.run(WEEKLY, now=ist(2026, 10, 12))        # switched to weekly: Mon 12 Oct
        assert (result.status, result.period) == (DONE, "2026-10-05_2026-10-11")
        assert env.sent_to[-1][1] == "AI Switch – Weekly programme report – 5–11 Oct 2026"


# Next release (retry + send log):
# class TestFrequencyChange:
#     """AC: "If the frequency is changed, the change takes effect from the next
#     reporting period" — and no day is reported twice."""
#
#     @pytest.mark.asyncio
#     async def test_monthly_to_weekly_starts_with_the_first_whole_week_after_the_month(self, env):
#         await env.run(MONTHLY, now=ist(2026, 10, 1))                 # September sent
#         # Switched to weekly on Tue 6 Oct: week 28 Sep–4 Oct overlaps September.
#         assert (await env.run(WEEKLY, now=ist(2026, 10, 6))).status == NOTHING_DUE
#         result = await env.run(WEEKLY, now=ist(2026, 10, 12))       # week 5–11 Oct: first weekly report
#         assert (result.status, result.period) == (DONE, "2026-10-05_2026-10-11")
#         assert env.sent_to[-1][1] == "AI Switch – Weekly programme report – 5–11 Oct 2026"
#
#     @pytest.mark.asyncio
#     async def test_weekly_to_monthly_waits_for_the_next_whole_month(self, env):
#         await env.run(WEEKLY, now=ist(2026, 10, 12))                 # 5–11 Oct sent
#         # Switched to monthly: October overlaps a sent week, so it is skipped...
#         assert (await env.run(MONTHLY, now=ist(2026, 11, 1))).status == NOTHING_DUE
#         # ...and November is the first monthly report.
#         result = await env.run(MONTHLY, now=ist(2026, 12, 1))
#         assert (result.status, result.period) == (DONE, "2026-11")
#
#     @pytest.mark.asyncio
#     async def test_due_period_ignores_the_period_being_delivered(self, env):
#         # A partly-sent period mustn't count as "already covered" for itself.
#         await env.log.record(SEP, "u1", None)
#         assert await due_period(env.log, MONTHLY, ist(2026, 10, 2), ANCHOR) == SEP


# ── run lock (live ai4iplatform_core; skipped without one) ──


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


# Next release (retry + send log):
# @pytest_asyncio.fixture()
# async def log_session(engine):
#     """A SendLog on a rolled-back transaction; creates the table inside it
#     when the DB isn't migrated yet."""
#     conn = await engine.connect()
#     trans = await conn.begin()
#     await conn.run_sync(lambda sync: UsageReportSendLog.__table__.create(sync, checkfirst=True))
#     await conn.execute(text("DELETE FROM usage_report_send_log"))
#     try:
#         yield SendLog(AsyncSession(bind=conn, join_transaction_mode="create_savepoint"))
#     finally:
#         await trans.rollback()
#         await conn.close()
#
#
# class TestSendLogSql:
#     @pytest.mark.asyncio
#     async def test_record_upserts_one_row_per_recipient_and_counts_attempts(self, log_session):
#         log = log_session
#         await log.record(SEP, "u1", "relay refused")
#         await log.record(SEP, "u1", None)
#         await log.record(SEP, "u2", None)
#         states = await log.recipient_states(SEP)
#         assert states == {"u1": RecipientState(SENT, 2), "u2": RecipientState(SENT, 1)}
#
#     @pytest.mark.asyncio
#     async def test_last_reported_end_skips_the_excluded_period_and_failures(self, log_session):
#         log = log_session
#         week = ReportPeriod.days(WEEKLY, date(2026, 10, 5), date(2026, 10, 11))
#         await log.record(SEP, "u1", None)
#         await log.record(week, "u1", "boom")              # FAILED only: not "reported"
#         await log.record_not_ready(week, "figures failed")
#         assert await log.last_reported_end(excluding=week) == SEP.end
#         assert await log.last_reported_end(excluding=SEP) is None


class TestRegistryCountsSql:
    @pytest.mark.asyncio
    async def test_grouped_count_matches_count_models_per_task_type(self, engine):
        # The one grouped query must agree with the per-type query it replaced.
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.repositories.model_management.model_repository import ModelRepository
        from app.services.metering_service import _to_registry_task_types
        from app.utils.metering_promql_builder import SERVICE_BREAKDOWN_CONFIG

        async with AsyncSession(engine) as session:
            if await session.scalar(text("SELECT to_regclass('mm_models')")) is None:
                pytest.skip("mm_models doesn't exist; migrate the DB first")
            repo = ModelRepository(session)
            grouped = await repo.count_models_by_task_type()
            checked = 0
            for task in SERVICE_BREAKDOWN_CONFIG:
                registry = _to_registry_task_types([task])
                if not registry:  # "pipeline": no Registry task type
                    continue
                actual = grouped.get(registry[0].lower(), 0)
                assert actual == await repo.count_models(task_types=registry), task
                checked += actual
            assert checked == sum(grouped.values())  # no model left uncounted


class TestRunLock:
    @pytest.mark.asyncio
    async def test_a_second_run_cannot_take_the_lock_until_the_first_releases_it(self, engine):
        async with report_lock(engine) as first:
            assert first is True
            async with report_lock(engine) as second:
                assert second is False
        async with report_lock(engine) as again:
            assert again is True


# ── without the usage_report_send_log table ──────────────────────────────────


class _NoSendLogTableSession:
    """A DB session as on a database without usage_report_send_log: any query
    on that table fails the way Postgres does."""

    def __init__(self):
        self.sql: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _check(self, stmt):
        sql = str(stmt)
        self.sql.append(sql)
        if "usage_report_send_log" in sql:
            raise RuntimeError('relation "usage_report_send_log" does not exist')

    async def execute(self, stmt, *a, **k):
        self._check(stmt)

    async def scalar(self, stmt, *a, **k):
        self._check(stmt)

    async def commit(self):
        pass


class TestWithoutSendLogTable:
    @pytest.mark.asyncio
    async def test_scheduled_run_sends_without_touching_usage_report_send_log(self, monkeypatch):
        # The failing scenario: with the table's migration dropped, any send-log
        # query fails ("relation does not exist") and nobody gets the report.
        from contextlib import asynccontextmanager

        import app.core.database as database
        from app.services.usage_report import scheduler

        sessions: list[_NoSendLogTableSession] = []

        def factory():
            def make():
                sessions.append(_NoSendLogTableSession())
                return sessions[-1]
            return make

        @asynccontextmanager
        async def lock(engine):
            yield True

        smtp = AsyncMock()
        monkeypatch.setattr("app.core.config.settings.prometheus_url", "http://prom:9090")
        monkeypatch.setattr("app.core.config.settings.portal_url", "https://portal.gov.in")
        monkeypatch.setattr(database, "get_primary_session_factory", factory, raising=False)
        monkeypatch.setattr(database, "get_auth_session_factory", factory, raising=False)
        monkeypatch.setattr(database, "get_engine", lambda: None, raising=False)
        monkeypatch.setattr("app.services.usage_report.send_log.report_lock", lock)
        monkeypatch.setattr("app.services.usage_report.collector.UsageReportCollector.collect",
                            AsyncMock(side_effect=lambda period, now=None: replace(_full_data(), period=period)))
        monkeypatch.setattr("app.services.usage_report.recipients.usage_viewers", AsyncMock(return_value=VIEWERS))
        monkeypatch.setattr("app.services.usage_report.mailer.email_settings", lambda: _email_cfg())
        monkeypatch.setattr("app.services.usage_report.pdf.render_report_pdf", lambda data: b"%PDF-1.4")
        monkeypatch.setattr("app.services.usage_report.mailer.aiosmtplib.send", smtp)

        result = await scheduler.run_scheduled_report("monthly", http_client=None, now=ist(2026, 10, 13))

        assert (result.status, result.period, result.sent, result.failed) == (DONE, "2026-09", ["u1", "u2"], [])
        assert smtp.await_count == 2
        assert not any("usage_report_send_log" in sql for sess in sessions for sql in sess.sql)

    def test_send_log_table_is_not_in_the_orm_metadata(self):
        # Keeps Alembic autogenerate from re-adding the table this release dropped.
        from app import models

        assert "usage_report_send_log" not in models.Base.metadata.tables
        assert "UsageReportSendLog" not in models.__all__


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
            "status": "done", "frequency": WEEKLY, "period": "2026-10-05_2026-10-11",
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
