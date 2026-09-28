"""consumers/notifications_consumer/emailer.py — send_one's never-raises
contract and its use of the one generic template.

No per-event dispatch left to pin here (see email_templates.py) — send_one
just builds a message via email_templates.render_email and reports whether
the send completed within its deadline. This suite covers: a successful
send, a timed-out send, a raising provider, and that ``details``/
``event_name``/``tenant_name`` land in the rendered message untouched.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from consumers.notifications_consumer import emailer
from consumers.notifications_consumer.emailer import Recipient


def _recipient() -> Recipient:
    return Recipient(email="a@b.com", display_name="Priya")


class TestSendOne:
    async def test_successful_send_returns_true(self):
        with patch.object(
            emailer, "_client", return_value=type(
                "C", (), {"send_safe": AsyncMock(return_value=True)}
            )(),
        ), patch.object(emailer, "_send_deadline_s", return_value=60.0):
            ok = await emailer.send_one(
                recipient=_recipient(), event_name="TIER_CHANGED", tenant_name="Acme Bank",
                details=["Silver", "Gold"],
            )
        assert ok is True

    async def test_send_safe_returning_false_is_reported_as_false(self):
        with patch.object(
            emailer, "_client", return_value=type(
                "C", (), {"send_safe": AsyncMock(return_value=False)}
            )(),
        ), patch.object(emailer, "_send_deadline_s", return_value=60.0):
            ok = await emailer.send_one(
                recipient=_recipient(), event_name="TIER_CHANGED", tenant_name="Acme Bank", details=[],
            )
        assert ok is False

    async def test_timeout_is_caught_and_reported_as_false(self):
        async def _hangs(*_a, **_kw):
            await asyncio.sleep(10)

        with patch.object(
            emailer, "_client", return_value=type("C", (), {"send_safe": _hangs})(),
        ), patch.object(emailer, "_send_deadline_s", return_value=0.01):
            ok = await emailer.send_one(
                recipient=_recipient(), event_name="TIER_CHANGED", tenant_name="Acme Bank", details=[],
            )
        assert ok is False

    async def test_render_or_send_exception_is_caught_and_reported_as_false(self):
        with patch(
            "consumers.notifications_consumer.emailer.email_templates.render_email",
            side_effect=RuntimeError("template blew up"),
        ):
            ok = await emailer.send_one(
                recipient=_recipient(), event_name="TIER_CHANGED", tenant_name="Acme Bank", details=[],
            )
        assert ok is False

    async def test_details_and_event_name_and_tenant_name_pass_through_untouched(self):
        with patch(
            "consumers.notifications_consumer.emailer.email_templates.render_email"
        ) as render, patch.object(
            emailer, "_client", return_value=type(
                "C", (), {"send_safe": AsyncMock(return_value=True)}
            )(),
        ), patch.object(emailer, "_send_deadline_s", return_value=60.0):
            await emailer.send_one(
                recipient=_recipient(), event_name="BUDGET_ASSIGNED", tenant_name="Acme Bank",
                details=["INR", "500000"],
            )

        render.assert_called_once_with(
            to="a@b.com", recipient_name="Priya", event_name="BUDGET_ASSIGNED",
            tenant_name="Acme Bank", details=["INR", "500000"],
        )
