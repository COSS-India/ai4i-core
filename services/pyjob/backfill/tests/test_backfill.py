"""backfill: windows, oldest-sample lookup, boundary-stop, PromQL, pricing and
the rows built from Prometheus samples. No database or Prometheus needed."""
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

# services/pyjob on the path, so `backfill`, `bootstrap` and `jobs` import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backfill.engine import (  # noqa: E402
    BackfillError,
    Lookups,
    Pricing,
    Service,
    _ist_midnight,
    build_rows,
    collect,
    first_whole_day,
    oldest_sample,
    path_task,
    queries,
    windows,
)

IST = ZoneInfo("Asia/Kolkata")
TIER = "5ab0c0de-0000-4000-8000-00000000000a"


def test_windows_one_per_ist_day_cut_at_until():
    spans = windows(date(2026, 10, 6), datetime(2026, 10, 8, 11, 30, tzinfo=IST))
    assert [(w.usage_date, w.start, w.end) for w in spans] == [
        (date(2026, 10, 6), datetime(2026, 10, 6, tzinfo=IST), datetime(2026, 10, 7, tzinfo=IST)),
        (date(2026, 10, 7), datetime(2026, 10, 7, tzinfo=IST), datetime(2026, 10, 8, tzinfo=IST)),
        (date(2026, 10, 8), datetime(2026, 10, 8, tzinfo=IST), datetime(2026, 10, 8, 11, 30, tzinfo=IST)),
    ]
    assert spans[-1].seconds == 11 * 3600 + 30 * 60


def test_windows_split_at_utc_month_start():
    # IST 1 Oct 00:00-05:30 is still September in UTC, as the consumer bills it.
    spans = windows(date(2026, 10, 1), datetime(2026, 10, 2, tzinfo=IST))
    assert [(w.usage_date, w.billing_month, w.seconds) for w in spans] == [
        (date(2026, 10, 1), "2026-09", 5 * 3600 + 1800),
        (date(2026, 10, 1), "2026-10", 18 * 3600 + 1800),
    ]
    assert spans[0].end == datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_windows_empty_when_until_is_before_the_first_day():
    assert windows(date(2026, 10, 8), datetime(2026, 10, 8, tzinfo=IST)) == []


def test_boundary_stop_excludes_the_cutover_day():
    # Cut-over = IST midnight of the first usage_events day: the cut-over day
    # itself is never backfilled, so no usage_date holds both sources.
    cutover = _ist_midnight(date(2026, 10, 8))
    spans = windows(date(2026, 10, 6), cutover)
    assert [w.usage_date for w in spans] == [date(2026, 10, 6), date(2026, 10, 7)]
    assert all(w.usage_date < date(2026, 10, 8) for w in spans)


class _FakePrometheus:
    """Has request-counter samples from ``oldest`` on, and no series to backfill."""

    def __init__(self, oldest):
        self.oldest = oldest

    async def query(self, promql, at):
        if "count_over_time" in promql:
            return [{"value": [at.timestamp(), "3"]}] if self.oldest is not None and at > self.oldest else []
        return []

    async def has_samples(self, metric, at):
        return bool(await self.query(f"count(count_over_time({metric}[1h]))", at))


_NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
_UNTIL = datetime(2026, 10, 8, 11, 30, tzinfo=IST)


@pytest.mark.asyncio
async def test_oldest_sample_is_looked_up_not_taken_from_retention():
    # Size eviction left data from 3 Oct 14:20 IST, whatever retention says.
    oldest = datetime(2026, 10, 3, 14, 20, tzinfo=IST)
    found = await oldest_sample(_FakePrometheus(oldest), _NOW)
    assert oldest < found <= oldest + timedelta(hours=1)
    assert first_whole_day(found) == date(2026, 10, 4)


@pytest.mark.asyncio
async def test_no_samples_at_all():
    assert await oldest_sample(_FakePrometheus(None), _NOW) is None


def test_the_first_day_starts_after_the_oldest_sample_and_its_lookback():
    # An oldest-sample hour ending just before midnight: that midnight is too close.
    assert first_whole_day(datetime(2026, 10, 3, 23, 55, tzinfo=IST)) == date(2026, 10, 5)
    assert first_whole_day(datetime(2026, 10, 3, 10, 0, tzinfo=IST)) == date(2026, 10, 4)


@pytest.mark.asyncio
async def test_collect_starts_on_the_first_whole_day_by_default():
    until = _ist_midnight(date(2026, 10, 8))
    collected = await collect(_FakePrometheus(datetime(2026, 10, 3, 14, 20, tzinfo=IST)), None, until)
    assert collected.first_day == date(2026, 10, 4)
    assert collected.days[0] == date(2026, 10, 4) and collected.days[-1] == date(2026, 10, 7)


@pytest.mark.asyncio
async def test_collect_boundary_stops_before_the_cutover_day(monkeypatch):
    from backfill import engine

    first_event = datetime(2026, 10, 8, 11, 30, tzinfo=IST)

    async def _fake_first_usage_event():
        return first_event

    monkeypatch.setattr(engine, "_first_usage_event", _fake_first_usage_event)
    # until unset → defaults to the cut-over (the first usage_events day's midnight).
    collected = await collect(_FakePrometheus(datetime(2026, 10, 3, 14, 20, tzinfo=IST)), None, None)
    assert collected.until == _ist_midnight(date(2026, 10, 8))
    assert date(2026, 10, 8) not in collected.days
    assert collected.days[-1] == date(2026, 10, 7)


@pytest.mark.asyncio
async def test_explicit_mid_day_until_is_clamped_to_ist_midnight():
    # A mid-day USAGE_BACKFILL_UNTIL must not give the cut-over day a partial
    # window: source isn't in the unique key, so the rollup would later
    # overwrite that row and a subsequent undo would wipe real recorded data.
    mid_day = datetime(2026, 10, 8, 11, 30, tzinfo=IST)
    collected = await collect(_FakePrometheus(datetime(2026, 10, 3, 14, 20, tzinfo=IST)), None, mid_day)
    assert collected.until == _ist_midnight(date(2026, 10, 8))
    assert date(2026, 10, 8) not in collected.days
    assert collected.days[-1] == date(2026, 10, 7)


@pytest.mark.asyncio
async def test_collect_refuses_a_first_day_prometheus_no_longer_has_the_start_of():
    with pytest.raises(BackfillError, match="overcount|lifetime"):
        await collect(_FakePrometheus(datetime(2026, 10, 3, 14, 20, tzinfo=IST)), date(2026, 10, 3), _UNTIL)


def test_queries_are_api_key_inference_traffic_on_the_path_label():
    by_kind = {(kind, task): q for kind, task, q in queries("exported_endpoint", 86400)}
    requests = by_kind[("requests", None)]
    assert 'exported_endpoint=~"(.*/inference|/api/v1/chat(/completions)?)"' in requests
    assert 'auth_type=~"api_key|"' in requests and 'tenant!="unknown"' in requests
    assert "increase(" in requests and "offset 86400s" in requests
    assert 'token_type=~"prompt|completion"' in by_kind[("llm", "llm")]
    assert "telemetry_obsv_asr_audio_minutes_processed_sum" in by_kind[("units", "asr")]


def test_path_task():
    assert path_task("/api/v1/chat/completions") == "llm"
    assert path_task("/api/v1/audio-lang-detection/inference") == "audio-lang-detection"
    assert path_task("/api/v1/speaker_diarization/inference") == "speaker-diarization"
    assert path_task("/api/v1/asr/inference") == "asr"
    assert path_task("/health") is None


def _lookups() -> Lookups:
    return Lookups(
        tenants={7: ("Org A", Decimal("5000.00"), TIER)},
        applications={11: "App single", 12: "App multi"},
        single_keys={11: 101},
        services={
            # ₹1 per 1000 input tokens, ₹3 per 1000 output tokens
            "llm-svc": Service("Chat", "Model X", Pricing(
                "llm", None, Decimal("1"), 1000, output_cost_per_unit=Decimal("3"),
            )),
            "asr-svc": Service("ASR", "Model Y", Pricing("asr", Decimal("0.5"), None, None)),
            "free-svc": Service("Free", None, Pricing("tts", None, None, None)),
        },
        inference_types={"llm": (1, "tokens"), "asr": (2, "audio_minutes"), "tts": (3, "characters")},
        tiers={TIER: "Gold"},
    )


def _sample(kind, value, task=None, day="2026-10-06", **labels):
    return {"usage_date": day, "billing_month": "2026-10", "kind": kind, "task": task,
            "labels": labels, "value": value}


def test_build_rows():
    samples = [
        _sample("requests", 9.6, tenant_id="7", application_id="11", service_id="llm-svc",
                path="/api/v1/chat/completions", status_code="200"),
        _sample("requests", 1.2, tenant_id="7", application_id="11", service_id="llm-svc",
                path="/api/v1/chat/completions", status_code="502"),
        _sample("llm", 8000.4, "llm", tenant_id="7", application_id="11", service_id="llm-svc", token_type="prompt"),
        _sample("llm", 2000, "llm", tenant_id="7", application_id="11", service_id="llm-svc", token_type="completion"),
        _sample("units", 3.123456, "asr", tenant_id="7", application_id="12", service_id="asr-svc"),
        _sample("units", 500, "tts", tenant_id="7", application_id="12", service_id="free-svc"),
        _sample("requests", 4, tenant_id="99", service_id="llm-svc", path="/api/v1/chat", status_code="200"),
    ]
    rows, skipped = build_rows(samples, _lookups())
    assert skipped == {"units: no price": 1, "requests: unknown tenant": 1}
    llm, asr = rows if rows[0]["service_id"] == "llm-svc" else rows[::-1]

    assert {k: llm[k] for k in (
        "usage_date", "tenant_id", "application_id", "api_key_id", "tier_id", "inference_type_id",
        "billing_month", "tenant_name", "application_name", "tier_name", "service_name", "model_name",
        "task_type", "unit", "request_count", "success_count", "failed_count",
    )} == {
        "usage_date": date(2026, 10, 6), "tenant_id": 7, "application_id": 11, "api_key_id": 101,
        "tier_id": TIER, "inference_type_id": 1, "billing_month": "2026-10", "tenant_name": "Org A",
        "application_name": "App single", "tier_name": "Gold", "service_name": "Chat",
        "model_name": "Model X", "task_type": "llm", "unit": "tokens",
        "request_count": 11, "success_count": 10, "failed_count": 1,
    }
    # 8000 input tokens at ₹1/1000 and 2000 output tokens at ₹3/1000; no cached input.
    assert (llm["total_units"], llm["output_units"], llm["cached_input_units"]) == (10000, 2000, 0)
    assert (llm["input_units_cost"], llm["output_units_cost"], llm["cached_input_units_cost"]) == (8, 6, 0)

    # Several keys on the application: no key. Minutes keep 4 dp, priced per minute.
    assert (asr["api_key_id"], asr["application_id"], asr["request_count"]) == (None, 12, 0)
    assert asr["total_units"] == Decimal("3.1235")
    assert asr["input_units_cost"] == Decimal("1.56175") and asr["output_units_cost"] == 0


def test_llm_output_falls_back_to_the_input_price():
    lookups = _lookups()
    lookups.services["llm-svc"].pricing = Pricing("llm", Decimal("0.002"), None, None)
    rows, _ = build_rows([
        _sample("llm", 100, "llm", tenant_id="7", service_id="llm-svc", token_type="prompt"),
        _sample("llm", 50, "llm", tenant_id="7", service_id="llm-svc", token_type="completion"),
    ], lookups)
    assert (rows[0]["input_units_cost"], rows[0]["output_units_cost"]) == (Decimal("0.2"), Decimal("0.1"))


def test_unknown_service_tier_and_application_become_null():
    lookups = _lookups()
    lookups.tenants[7] = ("Org A", None, "00000000-0000-4000-8000-000000000000")
    rows, skipped = build_rows([
        _sample("requests", 2, tenant_id="7", application_id="555", service_id="gone",
                path="/api/v1/asr/inference", status_code="200"),
    ], lookups)
    assert skipped == {}
    assert {k: rows[0][k] for k in ("application_id", "api_key_id", "tier_id", "service_id", "inference_type_id")} \
        == {"application_id": None, "api_key_id": None, "tier_id": None, "service_id": None, "inference_type_id": 2}


def test_rows_that_round_to_nothing_are_dropped():
    rows, _ = build_rows([
        _sample("requests", 0.3, tenant_id="7", service_id="llm-svc", path="/api/v1/chat", status_code="200"),
    ], _lookups())
    assert rows == []
