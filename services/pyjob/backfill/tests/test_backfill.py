"""backfill: the day's PromQL, LLM pricing, the rows built from a day's
Prometheus results, and the guard on which days may be backfilled. No
database or Prometheus needed (the guard's queries are faked)."""
import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

# services/pyjob on the path, so `backfill`, `bootstrap` and `jobs` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backfill import engine  # noqa: E402
from backfill.engine import (  # noqa: E402
    BackfillError, LlmService, Lookups, build_day_rows, check_days_not_recorded, day_queries,
    first_rollup_day, token_rates,
)

TIER = "5ab0c0de-0000-4000-8000-00000000000a"
DAY = date(2026, 10, 6)


def test_day_queries_are_the_dashboards_llm_api_key_queries():
    q = day_queries("exported_endpoint")
    for promql in q.values():
        assert 'tenant!="unknown"' in promql and 'auth_type=~"api_key|"' in promql
        assert "unless" in promql and "offset 86400s" in promql and "increase(" in promql
    assert 'exported_endpoint=~"/api/v1/chat(/completions)?"' in q["requests"]
    assert 'status_code=~"2.."' in q["successful"] and 'status_code' not in q["requests"]
    assert 'token_type=~"prompt|completion"' in q["tokens"]
    assert q["tokens"].startswith("sum by(tenant_id, application_id, service_id, token_type)")


def test_token_rates_as_the_consumer_prices_llm():
    # ₹1 per 1000 input tokens, ₹3 per 1000 output tokens.
    assert token_rates(None, 1, 1000, 3) == (Decimal("0.001"), Decimal("0.003"))
    # unit_rate wins for input; no output price → output priced like input.
    assert token_rates(Decimal("0.002"), 1, 1000, None) == (Decimal("0.002"), Decimal("0.002"))
    # No price at all.
    assert token_rates(None, None, None, None) == (Decimal(0), Decimal(0))


def _lookups() -> Lookups:
    return Lookups(
        tenants={7: ("Org A", Decimal("5000.00"), TIER)},
        applications={11: "App single", 12: "App multi"},
        single_keys={11: 101},
        tiers={TIER: "Gold"},
        services={"llm-svc": LlmService("Chat", "Model X", Decimal("0.001"), Decimal("0.003"))},
        llm_type_id=1,
        llm_unit="tokens",
    )


def _series(value, **labels):
    return {"metric": labels, "value": [0, str(value)]}


def test_one_row_per_institution_application_and_service():
    results = {
        "requests": [_series(10.6, tenant_id="7", application_id="11", service_id="llm-svc"),
                     _series(4, tenant_id="7", application_id="12", service_id="llm-svc")],
        "successful": [_series(9.4, tenant_id="7", application_id="11", service_id="llm-svc"),
                       _series(4, tenant_id="7", application_id="12", service_id="llm-svc")],
        "tokens": [_series(8000.4, tenant_id="7", application_id="11", service_id="llm-svc", token_type="prompt"),
                   _series(2000, tenant_id="7", application_id="11", service_id="llm-svc", token_type="completion")],
    }
    rows = {r["application_id"]: r for r in build_day_rows(DAY, results, _lookups())}

    single = rows[11]
    assert {k: single[k] for k in (
        "usage_date", "billing_month", "tenant_id", "tenant_name", "application_name", "api_key_id",
        "tier_id", "tier_name", "service_id", "service_name", "model_name", "inference_type_id",
        "task_type", "unit", "request_count", "success_count", "failed_count",
    )} == {
        "usage_date": DAY, "billing_month": "2026-10", "tenant_id": 7, "tenant_name": "Org A",
        "application_name": "App single", "api_key_id": 101, "tier_id": TIER, "tier_name": "Gold",
        "service_id": "llm-svc", "service_name": "Chat", "model_name": "Model X", "inference_type_id": 1,
        "task_type": "llm", "unit": "tokens", "request_count": 11, "success_count": 9, "failed_count": 2,
    }
    # 8000 input tokens at ₹0.001 and 2000 output tokens at ₹0.003.
    assert (single["total_units"], single["output_units"]) == (10000, 2000)
    assert (single["input_units_cost"], single["output_units_cost"]) == (8, 6)

    # Several keys on the application: no API key on the row.
    assert (rows[12]["api_key_id"], rows[12]["request_count"], rows[12]["total_units"]) == (None, 4, 0)


def test_unknown_application_service_and_tenant():
    results = {
        "requests": [_series(3, tenant_id="7", application_id="555", service_id="gone"),
                     _series(5, tenant_id="", application_id="11", service_id="llm-svc")],   # no tenant: skipped
        "successful": [],
        "tokens": [_series(100, tenant_id="7", application_id="555", service_id="gone", token_type="prompt")],
    }
    (row,) = build_day_rows(DAY, results, _lookups())
    assert {k: row[k] for k in ("application_id", "api_key_id", "service_id", "service_name")} == {
        "application_id": None, "api_key_id": None, "service_id": None, "service_name": None,
    }
    # Not an LLM service in mm_services: tokens kept, no price.
    assert (row["total_units"], row["input_units_cost"], row["failed_count"]) == (100, 0, 3)


def test_series_that_become_the_same_row_add_up():
    """Two applications missing from the auth DB (and two non-LLM services)
    under one institution are one row, not two rows with the same unique key."""
    results = {
        "requests": [_series(2.4, tenant_id="7", application_id="555", service_id="llm-svc"),
                     _series(3.4, tenant_id="7", application_id="666", service_id="llm-svc"),
                     _series(1, tenant_id="7", application_id="11", service_id="gone-a"),
                     _series(1, tenant_id="7", application_id="11", service_id="gone-b")],
        "successful": [_series(2.4, tenant_id="7", application_id="555", service_id="llm-svc"),
                       _series(1.4, tenant_id="7", application_id="666", service_id="llm-svc")],
        "tokens": [_series(100, tenant_id="7", application_id="555", service_id="llm-svc", token_type="prompt"),
                   _series(50, tenant_id="7", application_id="666", service_id="llm-svc", token_type="prompt"),
                   _series(10, tenant_id="7", application_id="666", service_id="llm-svc", token_type="completion")],
    }
    rows = build_day_rows(DAY, results, _lookups())
    keys = [(r["tenant_id"], r["application_id"], r["service_id"]) for r in rows]
    assert sorted(keys, key=str) == sorted([(7, None, "llm-svc"), (7, 11, None)], key=str)
    unknown_app = next(r for r in rows if r["application_id"] is None)
    # Summed before rounding: 2.4 + 3.4 = 5.8 → 6 requests, 2.4 + 1.4 = 3.8 → 4 successful.
    assert (unknown_app["request_count"], unknown_app["failed_count"]) == (6, 2)
    assert (unknown_app["total_units"], unknown_app["output_units"]) == (160, 10)
    assert unknown_app["input_units_cost"] == Decimal("0.150")       # 150 prompt tokens x 0.001
    unknown_svc = next(r for r in rows if r["service_id"] is None)
    assert (unknown_svc["request_count"], unknown_svc["input_units_cost"]) == (2, 0)


def test_rows_that_round_to_nothing_are_dropped():
    results = {"requests": [_series(0.3, tenant_id="7", application_id="11", service_id="llm-svc")],
               "successful": [], "tokens": []}
    assert build_day_rows(DAY, results, _lookups()) == []


# ── Which days may be backfilled ───────────────────────────────────────────

TODAY = date(2026, 10, 27)


def _fake_db(monkeypatch, rollup_days=(), event_days=()):
    """platform_core_session answering the guard's two queries: daily_usage
    rollup rows per day, then usage_events rows per day and task type."""
    results = [
        [SimpleNamespace(usage_date=d, n=n) for d, n in rollup_days],
        [SimpleNamespace(day=d, task_type=t, n=n) for d, t, n in event_days],
    ]

    class Session:
        async def execute(self, *_):
            rows = results.pop(0)
            return SimpleNamespace(all=lambda: rows)

    @asynccontextmanager
    async def session():
        yield Session()

    monkeypatch.setattr(engine, "platform_core_session", session)


def test_the_rollup_reaches_yesterday_and_its_lookback():
    assert first_rollup_day(TODAY, 2) == date(2026, 10, 24)


def test_days_the_rollup_still_reaches_are_refused(monkeypatch):
    _fake_db(monkeypatch)
    with pytest.raises(BackfillError, match="rollup's reach"):
        asyncio.run(check_days_not_recorded(date(2026, 10, 16), date(2026, 10, 24), TODAY, 2))


def test_days_with_recorded_rollup_rows_are_refused(monkeypatch):
    _fake_db(monkeypatch, rollup_days=[(date(2026, 10, 18), 5)])
    with pytest.raises(BackfillError, match=r"2026-10-18 \(5\)"):
        asyncio.run(check_days_not_recorded(date(2026, 10, 16), date(2026, 10, 18), TODAY, 2))


def test_a_day_with_usage_events_but_no_rollup_rows_is_allowed(monkeypatch):
    """The day recording started: its events cover only part of it."""
    _fake_db(monkeypatch, event_days=[(date(2026, 10, 16), "llm", 42), (date(2026, 10, 16), "nmt", 4)])
    asyncio.run(check_days_not_recorded(date(2026, 10, 16), date(2026, 10, 16), TODAY, 2))
