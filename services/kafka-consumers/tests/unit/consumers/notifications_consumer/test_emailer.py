"""consumers/notifications_consumer/emailer.py — the event_name -> template
dispatch in _build_message.

``details`` is a plain positional array now (design doc §9) — one already
display-ready value per template placeholder, in the exact order §9's table
specifies for that event_name. _build_message's only job is picking the
right email_templates.py renderer and plugging each position into its
matching keyword argument; it does no parsing or formatting of its own any
more (that used to live here — see git history — and moved to the producer
side on purpose). This suite pins the position -> keyword mapping for all 9
events, plus the short-array degrade-to-"—" behaviour and the
never-raises contract.
"""
from __future__ import annotations

import pytest

from consumers.notifications_consumer import emailer
from consumers.notifications_consumer.recipients import Recipient


def _recipient() -> Recipient:
    return Recipient(user_id="1", email="a@b.com", display_name="Priya")


class TestAt:
    def test_in_range_returns_value(self):
        assert emailer._at(["a", "b"], 0, "TEST_EVENT") == "a"
        assert emailer._at(["a", "b"], 1, "TEST_EVENT") == "b"

    def test_out_of_range_returns_missing_marker(self):
        assert emailer._at(["a"], 1, "TEST_EVENT") == emailer._MISSING

    def test_out_of_range_uses_custom_default(self):
        assert emailer._at([], 0, "TEST_EVENT", default=[]) == []

    def test_out_of_range_logs_a_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            emailer._at(["a"], 1, "TIER_ASSIGNED")
        assert "TIER_ASSIGNED" in caplog.text
        assert "1" in caplog.text


class TestBuildMessageDispatch:
    """One case per event_name this consumer handles — asserts the right
    email_templates.py renderer fired (via its distinctive subject format)
    and that every positional value landed in the right place."""

    def test_tier_assigned(self):
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="TIER_ASSIGNED",
            details=["Gold", "High-volume tier", ["ASR: 10,000 req/mo"], "1000", "2026-09-10", "2027-09-09"],
        )
        assert msg.subject == "Tier Assigned — Acme Bank"
        assert "Gold" in msg.html_body
        assert "High-volume tier" in msg.html_body
        assert "ASR: 10,000 req/mo" in msg.html_body
        assert "1000" in msg.html_body
        assert "2026-09-10" in msg.html_body
        assert "2027-09-09" in msg.html_body

    def test_tier_changed(self):
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="TIER_CHANGED",
            details=["Silver", "Gold", "Premium tier", ["NMT: 20,000 req/mo"], "2000", "2026-09-10", "2027-09-09"],
        )
        assert msg.subject == "Tier Reassignment — Acme Bank"
        assert "Silver" in msg.html_body and "Gold" in msg.html_body
        assert "Premium tier" in msg.html_body
        assert "NMT: 20,000 req/mo" in msg.html_body

    def test_budget_assigned(self):
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="BUDGET_ASSIGNED",
            details=["INR", "500000"],
        )
        assert msg.subject == "Budget Assigned — Acme Bank"
        assert "INR 500000" in msg.html_body

    def test_budget_updated(self):
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="BUDGET_UPDATED",
            details=["INR", "500000", "750000", "2026-09-10"],
        )
        assert msg.subject == "Budget Revised — Acme Bank"
        assert "INR 500000" in msg.html_body and "INR 750000" in msg.html_body
        assert "2026-09-10" in msg.html_body

    def test_quota_limit_updated(self):
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="QUOTA_LIMIT_UPDATED",
            details=["Gold", ["NMT: changed from 10000 to 15000"], "2026-10-01"],
        )
        assert msg.subject == "Quota Limit Updated — Acme Bank"
        assert "Gold" in msg.html_body
        assert "NMT: changed from 10000 to 15000" in msg.html_body
        assert "2026-10-01" in msg.html_body

    def test_quota_exhausted(self):
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="QUOTA_EXHAUSTED",
            details=["Gold", ["ASR: Quota Limit 10,000, Resets on 2026-10-01"]],
        )
        assert msg.subject == "Quota Exhausted — Acme Bank"
        assert "Gold" in msg.html_body
        assert "ASR: Quota Limit 10,000, Resets on 2026-10-01" in msg.html_body

    def test_budget_exhausted(self):
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="BUDGET_EXHAUSTED",
            details=["INR", "500000"],
        )
        assert msg.subject == "Budget Exhausted — Acme Bank"
        assert "INR 500000" in msg.html_body

    def test_quota_threshold(self):
        # current_value is the actual % of quota consumed (email_templates.py's
        # own docstring, AI4IDS-3027), not an absolute "X of Y" count.
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="QUOTA_THRESHOLD",
            details=["80", "2026-09-10 14:30 IST", "82% (NMT)"],
        )
        assert msg.subject == "Quota Threshold at 80% — Acme Bank"
        assert "2026-09-10 14:30 IST" in msg.html_body
        assert "82% (NMT)" in msg.html_body

    def test_budget_threshold(self):
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="BUDGET_THRESHOLD",
            details=["80", "2026-09-10 14:30 IST", "82%"],
        )
        assert msg.subject == "Budget Threshold at 80% — Acme Bank"
        assert "82%" in msg.html_body

    def test_unknown_event_name_raises(self):
        with pytest.raises(ValueError):
            emailer._build_message(
                recipient=_recipient(), institution_name="Acme Bank", event_name="SOMETHING_ELSE",
                details=[],
            )

    def test_short_array_degrades_to_missing_marker_instead_of_raising(self):
        """A producer that sends fewer values than this event_name needs
        (a bug, or a not-yet-updated producer) must not crash the send —
        the missing tail positions render as the "—" marker."""
        msg = emailer._build_message(
            recipient=_recipient(), institution_name="Acme Bank", event_name="BUDGET_ASSIGNED",
            details=["INR"],  # budget_amount missing
        )
        assert emailer._MISSING in msg.html_body


class TestSendOneNeverRaises:
    async def test_unknown_event_name_is_reported_as_false_not_raised(self):
        # send_one's contract is "never raises" — _build_message raising a
        # ValueError for an unmapped event_name must be caught here, same as
        # any other render/send failure.
        ok = await emailer.send_one(
            recipient=_recipient(), institution_name="Acme Bank", event_name="SOMETHING_ELSE", details=[],
        )
        assert ok is False
