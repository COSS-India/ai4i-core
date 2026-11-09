"""Live-DB tests for the Usage Dashboard's usage_events metering backend
(UsageEventsMeteringService over MeteringUsageRepository).

Run against a real Postgres migrated to head, inside a transaction that is
always rolled back — same approach and connection settings as
test_period_usage_repository.py; skipped when no database is reachable.

Seeds request rows (status, no units — one per request) and usage rows
(units, no status) the way the billing consumer writes them, plus a
daily_usage day, and checks every figure counts each request once.
"""
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.services.metering_service_usage_events import UsageEventsMeteringService
from app.utils.metering_promql_builder import AbsoluteRange
from app.utils.usage_period import IST, resolve_period

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

_ALEMBIC_ENV = (
    Path(__file__).resolve().parents[3]
    / "infrastructure" / "databases" / "migrations" / "postgres" / "alembic" / ".env"
)
_TENANT = 990201
_SERVICE = "test-mue/llm-svc"
_MODEL = "test-mue-llm-model"


def _setting(env: dict, name: str):
    for key in (f"CORE_SERVICE_DB_{name}", f"POSTGRES_{name}"):
        value = os.environ.get(key) or env.get(key)
        if value:
            return value
    return None


def _url() -> str:
    env = dotenv_values(_ALEMBIC_ENV) if dotenv_values is not None and _ALEMBIC_ENV.exists() else {}
    parts = {n: _setting(env, n) for n in ("USER", "PASSWORD", "HOST", "PORT")}
    if not all(parts.values()):
        pytest.skip("no ai4iplatform_core DB settings (CORE_SERVICE_DB_* / POSTGRES_*)")
    database = os.environ.get("CORE_SERVICE_DB_NAME") or env.get("CORE_SERVICE_DB_NAME") or "ai4iplatform_core"
    return (
        f"postgresql+asyncpg://{parts['USER']}:{parts['PASSWORD']}"
        f"@{parts['HOST']}:{parts['PORT']}/{database}"
    )


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine(_url(), connect_args={"timeout": 5})
    try:
        conn = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"could not connect to ai4iplatform_core: {exc}")
    trans = await conn.begin()
    try:
        if await conn.scalar(text("SELECT to_regclass('ix_usage_events_request_rows')")) is None:
            pytest.skip("usage_events request-row index missing; migrate the DB to head first")
        yield AsyncSession(bind=conn)
    finally:
        await trans.rollback()
        await conn.close()
        await engine.dispose()


def _mid(day: date) -> datetime:
    """IST midnight of ``day``, in UTC."""
    return datetime.combine(day, time(), tzinfo=IST).astimezone(timezone.utc)


_TODAY = datetime.now(IST).date()
_D3, _D4, _D5, _D6 = (_TODAY - timedelta(days=n) for n in (3, 4, 5, 6))


async def _llm_id(session) -> int:
    return await session.scalar(text("SELECT id FROM inference_types WHERE name = 'llm'"))


async def _add_service(session) -> None:
    await session.execute(text(
        "INSERT INTO mm_models (id, model_id, version, version_status, name, task, languages, domain,"
        " inference_endpoint, submitter, is_lang_detection_enabled, is_multilingual, training_dataset)"
        " VALUES (gen_random_uuid(), :m, 'v1', 'ACTIVE', :m, '{\"type\": \"llm\"}', '[]', '[]', '{}', '{}',"
        " false, false, '{}')"
    ), {"m": _MODEL})
    await session.execute(text(
        "INSERT INTO mm_services (id, service_id, name, model_id, model_version, endpoint,"
        " is_multilingual_enabled, task_type, cost_per_unit)"
        " VALUES (gen_random_uuid(), :s, :s, :m, 'v1', 'http://x/v1/chat/completions', false, 'llm', 1)"
    ), {"s": _SERVICE, "m": _MODEL})


async def _request(session, corr: str, at: datetime, status: int, type_id, service=_SERVICE) -> None:
    await session.execute(text(
        "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, service_id, inference_type_id,"
        " task_type, status_code, total_units) VALUES (:c, :at, :t, :s, :ty, 'llm', :st, 0)"
    ), {"c": corr, "at": at, "t": _TENANT, "s": service, "ty": type_id, "st": status})


async def _usage(session, corr: str, at: datetime, type_id, units, cached=0, output=0) -> None:
    await session.execute(text(
        "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, service_id, inference_type_id,"
        " task_type, status_code, total_units, cached_input_units, output_units, input_units_cost)"
        " VALUES (:c, :at, :t, :s, :ty, 'llm', NULL, :u, :cu, :ou, 0.5)"
    ), {"c": corr, "at": at, "t": _TENANT, "s": _SERVICE, "ty": type_id, "u": units, "cu": cached, "ou": output})


async def _daily(session, day: date, type_id, requests: int, failed: int, units) -> None:
    await session.execute(text(
        "INSERT INTO daily_usage (usage_date, billing_month, tenant_id, service_id, inference_type_id, task_type,"
        " request_count, success_count, failed_count, total_units, input_units_cost)"
        " VALUES (:d, :m, :t, :s, :ty, 'llm', :r, :ok, :f, :u, 1)"
    ), {"d": day, "m": day.strftime("%Y-%m"), "t": _TENANT, "s": _SERVICE, "ty": type_id,
        "r": requests, "ok": requests - failed, "f": failed, "u": units})


async def _seed(session) -> int:
    """D3: three requests (two 200, one 502), the successes with usage rows
    (the LLM one with a token split); D4: two requests, not rolled up; D5:
    only in daily_usage (four requests, one failed); D6: one request, so
    request rows cover D4 onwards from its start."""
    llm = await _llm_id(session)
    await _add_service(session)
    d3 = _mid(_D3)
    await _request(session, "mue-1", d3 + timedelta(hours=1, minutes=10), 200, llm)
    await _usage(session, "mue-1", d3 + timedelta(hours=1, minutes=9), llm, 300, cached=50, output=100)
    await _request(session, "mue-2", d3 + timedelta(hours=1, minutes=20), 502, llm)
    await _request(session, "mue-3", d3 + timedelta(hours=5), 200, llm)
    await _usage(session, "mue-3", d3 + timedelta(hours=4, minutes=59), llm, 100, output=40)
    d4 = _mid(_D4)
    await _request(session, "mue-4", d4 + timedelta(hours=2), 200, llm)
    await _request(session, "mue-5", d4 + timedelta(hours=3), 429, llm)
    await _daily(session, _D5, llm, requests=4, failed=1, units=Decimal("90"))
    await _request(session, "mue-6", _mid(_D6) + timedelta(hours=9), 200, llm)
    return llm


def _svc(session) -> UsageEventsMeteringService:
    return UsageEventsMeteringService(session)


def _day_range(day: date) -> AbsoluteRange:
    return AbsoluteRange(start=_mid(day), end=_mid(day + timedelta(days=1)))


@pytest.mark.asyncio
class TestRequestCounts:
    async def test_each_request_counted_once_from_its_request_row(self, session):
        await _seed(session)
        rt = await _svc(session).request_total(
            True, None, None, _day_range(_D3), tenant_id=str(_TENANT),
        )
        assert (rt["total_requests"]["count"], rt["successful_requests"]["count"],
                rt["failed_requests"]["count"]) == (3, 2, 1)
        assert rt["success_rate"]["rate_pct"] == 66.67
        assert rt["avg_rps"]["value"] == round(3 / 86_400, 4)

    async def test_previous_window_figures(self, session):
        """D3 vs D4 (the day before), covered by request rows from D6 on, so
        the previous figures are set."""
        await _seed(session)
        rt = await _svc(session).request_total(
            True, None, None, _day_range(_D3), tenant_id=str(_TENANT),
        )
        assert (rt["total_requests"]["previous_count"], rt["failed_requests"]["previous_count"]) == (2, 1)
        assert rt["total_requests"]["vs_previous_pct"] == 50.0

    async def test_task_filter(self, session):
        await _seed(session)
        svc = _svc(session)
        llm = await svc.request_total(True, None, None, _day_range(_D3), ["llm"], tenant_id=str(_TENANT))
        nmt = await svc.request_total(True, None, None, _day_range(_D3), ["nmt"], tenant_id=str(_TENANT))
        assert (llm["total_requests"]["count"], nmt["total_requests"]["count"]) == (3, 0)


async def _mark_fallback(session, corr: str) -> None:
    await session.execute(
        text("UPDATE usage_events SET sent_to_fallback = true WHERE correlation_id = :c"), {"c": corr},
    )


@pytest.mark.asyncio
class TestFallbackRequests:
    """The Institution tab's fallback-served count: part of the total, scoped
    and filtered like it, 0 when there were none."""

    async def test_counted_and_still_part_of_the_total(self, session):
        await _seed(session)
        await _mark_fallback(session, "mue-3")
        rt = await _svc(session).request_total(True, None, None, _day_range(_D3), tenant_id=str(_TENANT))
        assert rt["fallback_requests"]["count"] == 1
        assert rt["total_requests"]["count"] == 3   # unchanged

    async def test_zero_when_none_in_the_period(self, session):
        await _seed(session)
        await _mark_fallback(session, "mue-3")   # D3, outside the range below
        rt = await _svc(session).request_total(True, None, None, _day_range(_D4), tenant_id=str(_TENANT))
        assert (rt["fallback_requests"]["count"], rt["fallback_requests"]["formatted"]) == (0, "0")

    async def test_only_the_scoped_institution(self, session):
        await _seed(session)
        await _mark_fallback(session, "mue-3")
        other = await _svc(session).request_total(
            True, None, None, _day_range(_D3), tenant_id=str(_TENANT + 1),
        )
        assert other["fallback_requests"]["count"] == 0

    async def test_previous_is_none_before_fallbacks_were_recorded(self, session):
        """D3 vs D4: no request row before D4 has a response time, so D4's 0
        is not a real figure."""
        await _seed(session)
        await _mark_fallback(session, "mue-3")
        fb = (await _svc(session).request_total(
            True, None, None, _day_range(_D3), tenant_id=str(_TENANT),
        ))["fallback_requests"]
        assert (fb["previous_count"], fb["previous_formatted"], fb["vs_previous_pct"]) == (None, None, None)

    async def test_previous_is_set_once_fallbacks_were_recorded(self, session):
        await _seed(session)
        await _mark_fallback(session, "mue-3")
        await session.execute(
            text("UPDATE usage_events SET response_time_ms = 120 WHERE correlation_id = 'mue-6'"),
        )
        fb = (await _svc(session).request_total(
            True, None, None, _day_range(_D3), tenant_id=str(_TENANT),
        ))["fallback_requests"]
        assert (fb["previous_count"], fb["previous_formatted"]) == (0, "0")

    async def test_rolled_up_days_add_fallback_count(self, session):
        """D5 is only in daily_usage, D3 only in usage_events: both count."""
        await _seed(session)
        await _mark_fallback(session, "mue-3")
        await session.execute(
            text("UPDATE daily_usage SET fallback_count = 2 WHERE usage_date = :d AND tenant_id = :t"),
            {"d": _D5, "t": _TENANT},
        )
        week = AbsoluteRange(start=_mid(_TODAY - timedelta(days=7)), end=_mid(_TODAY))
        rt = await _svc(session).request_total(True, None, None, week, tenant_id=str(_TENANT))
        assert rt["fallback_requests"]["count"] == 3


@pytest.mark.asyncio
class TestChart:
    async def test_hourly_buckets_from_usage_events(self, session):
        await _seed(session)
        graph = await _svc(session).request_volume_chart(_day_range(_D3), None, tenant_id=str(_TENANT))

        assert graph.step == "1h"
        succ, fail = (s.points for s in graph.series)
        assert len(succ) == 24 and succ[0].ts == int(_mid(_D3).timestamp())
        assert (succ[1].value, fail[1].value, succ[5].value) == (1, 1, 1)
        assert sum(p.value for p in succ) == 2 and sum(p.value for p in fail) == 1

    async def test_daily_buckets_mix_rollup_and_usage_events(self, session):
        """D5 is only in daily_usage, D4 and D3 only in usage_events (not
        rolled up): every day shows, none as zero."""
        await _seed(session)
        week = AbsoluteRange(start=_mid(_TODAY - timedelta(days=7)), end=_mid(_TODAY))
        graph = await _svc(session).request_volume_chart(week, None, tenant_id=str(_TENANT))

        assert graph.step == "1d"
        succ, fail = ({p.ts: p.value for p in s.points} for s in graph.series)
        assert len(succ) == 7
        at = lambda d: int(_mid(d).timestamp())   # noqa: E731
        assert (succ[at(_D5)], fail[at(_D5)]) == (3, 1)
        assert (succ[at(_D4)], fail[at(_D4)]) == (1, 1)
        assert (succ[at(_D3)], fail[at(_D3)]) == (2, 1)


@pytest.mark.asyncio
class TestModelBreakdown:
    async def test_requests_success_and_llm_tokens_per_service(self, session):
        await _seed(session)
        breakdown = await _svc(session).model_breakdown(
            None, _day_range(_D3), tenant_id=str(_TENANT),
        )
        (row,) = [s for s in breakdown["services"] if s["service_id"] == _SERVICE]
        assert (row["requests"], row["success_pct"], row["task_type"]) == (3, 66.67, "llm")
        assert row["native_units"] == 400
        assert {e["key"]: e["units"] for e in row["native_breakdown"]} == {
            "input": 210, "cached_input": 50, "output": 140,
        }


@pytest.mark.asyncio
class TestTenantsAndCoverage:
    async def test_concentration_and_active_tenants(self, session):
        await _seed(session)
        svc = _svc(session)
        conc = await svc.usage_concentration(50, _day_range(_D3))
        mine = [t for t in conc["top_tenants"] if t["tenant"] == str(_TENANT)]
        assert mine and mine[0]["requests"] == 3

    async def test_data_since(self, session):
        await _seed(session)
        svc = _svc(session)
        # Request rows from before D3 cover it from its start.
        d3 = resolve_period("custom", _D3.isoformat(), _D3.isoformat())
        assert await svc.data_since(d3) == d3.start
        # Long before any request row: no data.
        old = resolve_period("custom", "2001-01-01", "2001-01-02")
        assert await svc.data_since(old) is None


@pytest.mark.asyncio
class TestPreviousWindowCoverage:
    async def test_no_previous_figures_before_request_rows_begin(self, session):
        """The day before the first request row: not covered, so None —
        rather than a comparison against a day with no request rows."""
        llm = await _llm_id(session)
        await _add_service(session)
        if await session.scalar(text(
            "SELECT 1 FROM usage_events WHERE status_code IS NOT NULL AND total_units = 0"
            " AND occurred_at < :d LIMIT 1"
        ), {"d": _mid(_D3)}):
            pytest.skip("the database already holds request rows from before D3")
        await _request(session, "mue-x", _mid(_D3) + timedelta(hours=1), 200, llm)
        rt = await _svc(session).request_total(True, None, None, _day_range(_D3), tenant_id=str(_TENANT))
        assert rt["total_requests"]["count"] == 1
        assert rt["total_requests"]["previous_count"] is None


@pytest.mark.asyncio
class TestRequestRowCounting:
    """Request rows are counted one per row, not by distinct correlation id:
    a client can reuse one X-Correlation-ID across calls, and each call is
    still a request (as Prometheus counted). Rows from before the cut-over
    stand in for their request and are still counted by correlation id."""

    async def test_reused_correlation_id_counts_every_request(self, session):
        llm = await _llm_id(session)
        await _add_service(session)
        base = _mid(_D3) + timedelta(hours=1)
        await _request(session, "mue-reused", base, 200, llm)
        await _request(session, "mue-reused", base + timedelta(seconds=30), 502, llm)
        rt = await _svc(session).request_total(True, None, None, _day_range(_D3), tenant_id=str(_TENANT))
        assert (rt["total_requests"]["count"], rt["failed_requests"]["count"]) == (2, 1)

        graph = await _svc(session).request_volume_chart(_day_range(_D3), None, tenant_id=str(_TENANT))
        succ, fail = (s.points for s in graph.series)
        assert (succ[1].value, fail[1].value) == (1, 1)

    async def test_pre_cutover_rows_count_once_per_request(self, session):
        """Old-style rows (a status and units): a chunked request's two rows
        are one request."""
        llm = await _llm_id(session)
        await _add_service(session)
        base = _mid(_D3) + timedelta(hours=2)
        for i, units in enumerate((40, 60)):
            await session.execute(text(
                "INSERT INTO usage_events (correlation_id, occurred_at, tenant_id, service_id, inference_type_id,"
                " task_type, status_code, total_units) VALUES ('mue-old', :at, :t, :s, :ty, 'llm', 200, :u)"
            ), {"at": base + timedelta(seconds=i), "t": _TENANT, "s": _SERVICE, "ty": llm, "u": units})
        rt = await _svc(session).request_total(True, None, None, _day_range(_D3), tenant_id=str(_TENANT))
        assert rt["total_requests"]["count"] == 1


async def _drop(session, *days: date) -> None:
    """Drop ``days``' usage_events rows, as pyjob's retention does once they
    are rolled up (rolled back with the test's transaction)."""
    for day in days:
        await session.execute(
            text("DELETE FROM usage_events WHERE occurred_at >= :s AND occurred_at < :e"),
            {"s": _mid(day), "e": _mid(day + timedelta(days=1))},
        )


@pytest.mark.asyncio
class TestDroppedDays:
    """Days past usage_events' retention: dropped by pyjob, only in daily_usage."""

    async def test_a_range_starting_mid_day_counts_the_dropped_day_whole(self, session):
        """D5 can't be cut at 12:00 any more: the range runs to its end, so the
        whole day counts; the range ending at 12:00 leaves it out, so
        back-to-back ranges count it once."""
        await _seed(session)
        await _drop(session, _D5)
        noon = _mid(_D5) + timedelta(hours=12)
        svc = _svc(session)
        after = await svc.request_total(
            True, None, None, AbsoluteRange(start=noon, end=_mid(_D4)), tenant_id=str(_TENANT),
        )
        before = await svc.request_total(
            True, None, None, AbsoluteRange(start=_mid(_D6), end=noon), tenant_id=str(_TENANT),
        )
        assert after["total_requests"]["count"] == 4
        assert before["total_requests"]["count"] == 1    # D6's request only

    async def test_dropped_whole_days_read_daily_usage_only(self, session):
        """A dropped day's late rows, still waiting in usage_events for the
        next run to add them, don't count twice."""
        llm = await _seed(session)
        await _drop(session, _D5)
        await _request(session, "mue-late", _mid(_D5) + timedelta(hours=3), 200, llm)
        rt = await _svc(session).request_total(True, None, None, _day_range(_D5), tenant_id=str(_TENANT))
        assert rt["total_requests"]["count"] == 4

    async def test_no_hourly_chart_for_a_dropped_day(self, session):
        await _seed(session)
        await _drop(session, _D5)
        assert await _svc(session).request_volume_chart(_day_range(_D5), None, tenant_id=str(_TENANT)) is None

    async def test_data_since_from_dropped_days(self, session):
        """Once a day's request rows are dropped, its rollup tells when data
        begins: a dropped day before the range covers it, else the first
        dropped day inside it begins at its midnight."""
        llm = await _llm_id(session)
        await _add_service(session)
        if await session.scalar(text(
            "SELECT 1 FROM usage_events WHERE status_code IS NOT NULL AND total_units = 0"
            " AND occurred_at < :d LIMIT 1"
        ), {"d": _mid(_TODAY)}):
            pytest.skip("the database already holds request rows from before today")
        await _daily(session, _D6, llm, requests=2, failed=0, units=0)
        await _daily(session, _D5, llm, requests=3, failed=0, units=0)
        await _drop(session, _D6, _D5)
        await _request(session, "mue-kept", _mid(_D4) + timedelta(hours=1), 200, llm)
        svc = _svc(session)

        d5 = resolve_period("custom", _D5.isoformat(), _D5.isoformat())
        assert await svc.data_since(d5) == d5.start          # D6 before it
        d6_d4 = resolve_period("custom", _D6.isoformat(), _D4.isoformat())
        assert await svc.data_since(d6_d4) == d6_d4.start    # begins on D6, a dropped day
        rt = await svc.request_total(True, None, None, _day_range(_D5), tenant_id=str(_TENANT))
        assert rt["total_requests"]["previous_count"] == 2   # D6 vs D5: covered

    async def test_fallbacks_recorded_by_from_dropped_days(self, session):
        llm = await _llm_id(session)
        await _add_service(session)
        if await session.scalar(text(
            "SELECT 1 FROM usage_events WHERE status_code IS NOT NULL AND total_units = 0"
            " AND occurred_at < :d LIMIT 1"
        ), {"d": _mid(_D4)}):
            pytest.skip("the database already holds request rows from before D4")
        if await session.scalar(text(
            "SELECT 1 FROM daily_usage WHERE source = 'rollup' AND response_time_count > 0"
            " AND usage_date < :d LIMIT 1"
        ), {"d": _D4}):
            pytest.skip("the database already holds rolled-up response times from before D4")
        await _daily(session, _D6, llm, requests=2, failed=0, units=0)
        await _drop(session, _D6)
        repo = _svc(session)._usage
        assert await repo.fallbacks_recorded_by(_mid(_D4)) is False
        await session.execute(text(
            "UPDATE daily_usage SET response_time_count = 2, total_response_time_ms = 240"
            " WHERE usage_date = :d AND tenant_id = :t"
        ), {"d": _D6, "t": _TENANT})
        assert await repo.fallbacks_recorded_by(_mid(_D4)) is True

    async def test_first_request_from_the_rollup_once_usage_events_dropped_it(self, session):
        llm = await _seed(session)
        await _daily(session, _TODAY - timedelta(days=40), llm, requests=1, failed=0, units=0)
        first = await _svc(session).first_request_at(None, tenant_id=str(_TENANT))
        assert first == _mid(_TODAY - timedelta(days=40))

    async def test_first_request_keeps_its_exact_time_while_usage_events_has_the_day(self, session):
        await _seed(session)     # D5 in daily_usage; D6's request at 09:00 in usage_events
        await _daily(session, _D6, await _llm_id(session), requests=1, failed=0, units=0)
        first = await _svc(session).first_request_at(None, tenant_id=str(_TENANT))
        assert first == _mid(_D6) + timedelta(hours=9)
