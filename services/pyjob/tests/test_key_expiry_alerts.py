"""jobs/key_expiry_alerts.py — the daily GRACE_PERIOD_EXPIRING /
API_KEY_EXPIRING reminder step.

The candidate SQL itself runs against Postgres; here the page reader and
emit_state_bulk are stubbed to check what the step builds and sends."""
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai4i_core.kafka import NotificationName, Severity, ThresholdUnit  # noqa: E402
from ai4i_core.kafka.cache import CacheRead  # noqa: E402
from ai4i_core.kafka.models import Band  # noqa: E402

from bootstrap import notifications as notif  # noqa: E402
from jobs import key_expiry_alerts as step  # noqa: E402

GRACE = NotificationName.GRACE_PERIOD_EXPIRING
EXPIRING = NotificationName.API_KEY_EXPIRING
DAY_BANDS = (
    Band(Decimal(1), ThresholdUnit.DAYS, Severity.CRITICAL),
    Band(Decimal(5), ThresholdUnit.DAYS, Severity.WARNING),
    Band(Decimal(10), ThresholdUnit.DAYS, Severity.INFO),
)


@pytest.fixture(autouse=True)
def tz(monkeypatch):
    monkeypatch.setattr(step.get_settings(), "NOTIFICATION_TIMEZONE", "Asia/Kolkata")


def _row(key_id: int, days_before: int, days_left: int, tenant_id: int = 7) -> dict:
    return {
        "api_key_id": key_id,
        "key_name": f"key-{key_id}",
        "expiring_key": f"ab12{key_id:024d}gh78",
        "new_key": None,
        "expires_at": datetime(2026, 11, 27, 10, 30, 15, 123456, tzinfo=timezone.utc),
        "application_name": "Billing App",
        "tenant_id": tenant_id,
        "tenant_name": "Force India",
        "days_left": days_left,
        "days_before": days_before,
    }


@asynccontextmanager
async def _lock_session(locked=True):
    session = MagicMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar=lambda: locked))
    yield session


@pytest.fixture
def runtime(monkeypatch):
    rt = MagicMock()
    snapshot = MagicMock()
    snapshot.get = lambda name: SimpleNamespace(bands=DAY_BANDS)

    async def read(**kwargs):
        return CacheRead(settings=snapshot)

    rt.cache.read = read
    rt.auth_session_factory = _lock_session
    monkeypatch.setattr(step, "get_notification_runtime", lambda: rt)
    monkeypatch.setattr(step, "notifications_configured", lambda: True)
    return rt


def test_day_levels_keeps_days_bands_only():
    levels, severity = step.day_levels(DAY_BANDS + (Band(Decimal(50), ThresholdUnit.PERCENT, Severity.INFO),))
    assert levels == [1, 5, 10]
    assert severity == {1: Severity.CRITICAL, 5: Severity.WARNING, 10: Severity.INFO}


def test_email_datetime_is_in_notification_timezone():
    assert step.email_datetime(datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)) == "27 Nov 2026, 04:00 PM IST"


def test_state_item():
    _, severity = step.day_levels(DAY_BANDS)
    item = step._state_item(_row(901, 5, 4), severity)
    assert item.tenant_id == "7"
    assert item.subject == {"api_key_id": "901", "expires_at": "2026-11-27T10:30:15Z", "days_before": "5"}
    assert item.new_state == {"days_before": 5}
    assert item.severity is Severity.WARNING
    assert item.tenant_name == "Force India"
    # [application, masked key, expiry, days left]
    assert item.details == ["Billing App", "ab12******gh78", "27 Nov 2026, 04:00 PM IST", 4]


def test_grace_details_add_the_masked_new_key():
    _, severity = step.day_levels(DAY_BANDS)
    row = {**_row(903, 10, 9), "new_key": "cd34" + "0" * 24 + "ij90"}
    item = step._state_item(row, severity)
    # [application, masked old key, expiry, days left, masked new key]
    assert item.details == ["Billing App", "ab12******gh78", "27 Nov 2026, 04:00 PM IST", 9, "cd34******ij90"]
    assert all(row["expiring_key"] not in str(d) and row["new_key"] not in str(d) for d in item.details)


@pytest.mark.parametrize("value,masked", [
    ("ab12cd34ef56gh78", "ab12******gh78"),
    ("short", "********"),
    (None, None),
])
def test_mask_api_key(value, masked):
    assert step.mask_api_key(value) == masked


def test_last_day_is_critical():
    _, severity = step.day_levels(DAY_BANDS)
    item = step._state_item(_row(902, 1, 1), severity)
    assert item.severity is Severity.CRITICAL
    assert item.details[3] == 1


@pytest.mark.asyncio
async def test_pages_until_a_short_page_and_sends_each_page(runtime, monkeypatch):
    monkeypatch.setattr(step, "PAGE_SIZE", 2)
    pages = {0: [_row(1, 10, 10), _row(2, 5, 5)], 2: [_row(3, 1, 1)]}
    seen_after = []

    async def page(name, levels, after_id):
        seen_after.append(after_id)
        assert levels == [1, 5, 10]
        return pages.get(after_id, [])

    sent_batches = []

    async def emit(name, items, **kwargs):
        sent_batches.append((name, items))
        return [object() for _ in items]

    monkeypatch.setattr(step, "_candidate_page", page)
    monkeypatch.setattr(step, "emit_state_bulk", emit)

    result = await step.send_reminders((GRACE,))

    assert seen_after == [0, 2]
    assert [len(items) for _, items in sent_batches] == [2, 1]
    grace = result.results[GRACE.value]
    assert (grace.candidates, grace.sent, grace.levels) == (3, 3, [1, 5, 10])


@pytest.mark.asyncio
async def test_both_alerts_run_by_default(runtime, monkeypatch):
    names = []

    async def page(name, levels, after_id):
        names.append(name)
        return []

    monkeypatch.setattr(step, "_candidate_page", page)
    result = await step.send_reminders()
    assert names == [GRACE, EXPIRING]
    assert set(result.results) == {GRACE.value, EXPIRING.value}


@pytest.mark.asyncio
async def test_no_days_thresholds_skips_the_alert(runtime, monkeypatch):
    runtime.cache.read = AsyncMock(
        return_value=CacheRead(settings=SimpleNamespace(get=lambda name: SimpleNamespace(bands=())))
    )
    page = AsyncMock()
    monkeypatch.setattr(step, "_candidate_page", page)

    result = await step.send_reminders((GRACE,))

    page.assert_not_awaited()
    assert result.results[GRACE.value].candidates == 0


@pytest.mark.asyncio
async def test_locked_run_is_skipped(runtime, monkeypatch):
    runtime.auth_session_factory = lambda: _lock_session(locked=False)
    page = AsyncMock()
    monkeypatch.setattr(step, "_candidate_page", page)

    result = await step.send_reminders()

    assert result.skipped == "locked"
    page.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_when_notifications_are_off(monkeypatch):
    monkeypatch.setattr(step, "notifications_configured", lambda: False)
    with pytest.raises(step.ExpiryAlertsUnavailable):
        await step.send_reminders()


@pytest.mark.asyncio
async def test_unavailable_when_settings_cannot_be_read(runtime):
    runtime.cache.read = AsyncMock(return_value=CacheRead(settings=None, settings_error="redis down"))
    with pytest.raises(step.ExpiryAlertsUnavailable, match="redis down"):
        await step.send_reminders()


@pytest.mark.asyncio
async def test_notifications_need_their_settings(monkeypatch):
    settings = notif.get_settings()
    monkeypatch.setattr(settings, "KAFKA_SERVER", None)
    monkeypatch.setattr(settings, "PII_ENCRYPTION_KEY", None)
    with pytest.raises(RuntimeError, match="KAFKA_SERVER, PII_ENCRYPTION_KEY"):
        async with notif.notifications():
            pass


@pytest.mark.asyncio
async def test_run_wraps_the_reminders_in_the_pipeline(monkeypatch):
    calls = []

    @asynccontextmanager
    async def pipeline():
        calls.append("start")
        yield
        calls.append("stop")

    async def send():
        calls.append("send")
        return step.RunResult()

    monkeypatch.setattr(step, "notifications", pipeline)
    monkeypatch.setattr(step, "send_reminders", send)
    await step.run()
    assert calls == ["start", "send", "stop"]
