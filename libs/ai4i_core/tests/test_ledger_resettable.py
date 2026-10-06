"""ai4i_core/kafka/ledger.py — Q-L9 resettable_subjects.

The open incidents a monitoring quiet tick may reset: the same cooldown
predicate as the Q-L3 RESET, grouped by notification row, subjects parsed
whether the driver returns JSONB as a dict or as text.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai4i_core.kafka import ledger, resettable_subjects


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((statement, params))
        return SimpleNamespace(mappings=lambda: iter(self.rows))


def test_listing_and_reset_share_one_cooldown_predicate():
    assert ledger._RESETTABLE in str(ledger._RESET_SQL)
    assert ledger._RESETTABLE in str(ledger._RESETTABLE_SQL)


@pytest.mark.asyncio
async def test_subjects_are_grouped_by_notification_row():
    session = _Session([
        {"notification_id": 14, "subject": {"service_id": "svc-a"}},
        {"notification_id": 14, "subject": '{"service_id": "svc-b"}'},
        {"notification_id": 10, "subject": {"service_id": "svc-a"}},
    ])

    result = await resettable_subjects(session, [10, 14], "PLATFORM", 1800)

    assert result == {
        14: [{"service_id": "svc-a"}, {"service_id": "svc-b"}],
        10: [{"service_id": "svc-a"}],
    }
    (_, params), = session.calls
    assert params == {"notification_ids": [10, 14], "tenant_id": "PLATFORM", "cooldown_s": 1800}


@pytest.mark.asyncio
async def test_no_rows_asked_reads_nothing():
    session = _Session([])

    assert await resettable_subjects(session, [], "PLATFORM", 1800) == {}
    assert session.calls == []
