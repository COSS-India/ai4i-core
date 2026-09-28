"""consumers/notifications_consumer/delivery.py — maps envelope recipients
onto emailer.send_one and reports whether at least one actually went out.

No lookups here any more (no auth_db, no institution_name fetch) — just
fan-out over the recipients list the envelope already carries.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from consumers.notifications_consumer import delivery


class TestDeliver:
    async def test_no_recipients_returns_false_without_calling_emailer(self):
        with patch(
            "consumers.notifications_consumer.delivery.emailer.send_one", AsyncMock()
        ) as send_one:
            ok = await delivery.deliver(
                tenant_name="Acme Bank", recipients=[], event_name="TIER_CHANGED", details=[],
            )
        assert ok is False
        send_one.assert_not_awaited()

    async def test_recipients_missing_email_key_are_skipped(self):
        with patch(
            "consumers.notifications_consumer.delivery.emailer.send_one", AsyncMock()
        ) as send_one:
            ok = await delivery.deliver(
                tenant_name="Acme Bank", recipients=[{"name": "no email here"}],
                event_name="TIER_CHANGED", details=[],
            )
        assert ok is False
        send_one.assert_not_awaited()

    async def test_at_least_one_success_reports_true(self):
        with patch(
            "consumers.notifications_consumer.delivery.emailer.send_one",
            AsyncMock(side_effect=[False, True]),
        ):
            ok = await delivery.deliver(
                tenant_name="Acme Bank",
                recipients=[
                    {"email": "a@example.com", "name": "A"},
                    {"email": "b@example.com", "name": "B"},
                ],
                event_name="TIER_CHANGED", details=["x"],
            )
        assert ok is True

    async def test_all_failing_reports_false(self):
        with patch(
            "consumers.notifications_consumer.delivery.emailer.send_one",
            AsyncMock(return_value=False),
        ):
            ok = await delivery.deliver(
                tenant_name="Acme Bank",
                recipients=[{"email": "a@example.com", "name": "A"}],
                event_name="TIER_CHANGED", details=[],
            )
        assert ok is False

    async def test_one_recipient_raising_does_not_prevent_others_from_succeeding(self):
        with patch(
            "consumers.notifications_consumer.delivery.emailer.send_one",
            AsyncMock(side_effect=[RuntimeError("boom"), True]),
        ):
            ok = await delivery.deliver(
                tenant_name="Acme Bank",
                recipients=[
                    {"email": "a@example.com", "name": "A"},
                    {"email": "b@example.com", "name": "B"},
                ],
                event_name="TIER_CHANGED", details=[],
            )
        assert ok is True

    async def test_recipient_with_no_name_falls_back_to_generic_greeting(self):
        with patch(
            "consumers.notifications_consumer.delivery.emailer.send_one", AsyncMock(return_value=True)
        ) as send_one:
            await delivery.deliver(
                tenant_name="Acme Bank",
                recipients=[{"email": "a@example.com"}],
                event_name="TIER_CHANGED", details=[],
            )

        person = send_one.await_args.kwargs["recipient"]
        assert person.email == "a@example.com"
        assert person.display_name == "there"
