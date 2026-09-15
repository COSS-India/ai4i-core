"""consumers/notifications_consumer/recipients.py — fetch_institution_name.

Every rendered email's subject line and body need "[Institution Name]"
(design doc §9.5's "Not part of details" note); this is the consumer's own
lookup for it (tenants.organisation), independent of what the producer
sends. Both its fallback paths (a non-numeric tenant_id, or no
matching/empty organisation) return the raw tenant_id string rather than
raising — that value lands directly in the subject line of every email for
that tenant, so it's worth pinning explicitly, not just leaving as an
implied side effect of "doesn't crash".
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from consumers.notifications_consumer.recipients import fetch_institution_name


def _db(row_value=None) -> AsyncMock:
    """A db whose single execute() call returns `row_value` from .first()
    (None simulates no matching tenant row)."""
    db = AsyncMock()
    result = MagicMock()
    result.first.return_value = row_value
    db.execute = AsyncMock(return_value=result)
    return db


class TestFetchInstitutionName:
    async def test_successful_lookup_returns_organisation_name(self):
        db = _db(row_value=("Acme Bank",))
        assert await fetch_institution_name(db, tenant_id="2") == "Acme Bank"

    async def test_non_numeric_tenant_id_falls_back_to_raw_id_without_querying(self):
        db = _db()
        result = await fetch_institution_name(db, tenant_id="not-a-number")
        assert result == "not-a-number"
        db.execute.assert_not_awaited()

    async def test_no_matching_row_falls_back_to_raw_tenant_id(self):
        db = _db(row_value=None)
        assert await fetch_institution_name(db, tenant_id="999") == "999"

    async def test_empty_organisation_falls_back_to_raw_tenant_id(self):
        # A row exists but organisation is empty/None — same degrade as no
        # row at all, not an empty-string subject line.
        db = _db(row_value=("",))
        assert await fetch_institution_name(db, tenant_id="2") == "2"

    async def test_queries_by_integer_tenant_id(self):
        db = _db(row_value=("Acme Bank",))
        await fetch_institution_name(db, tenant_id="2")
        # execute(stmt, {"tenant_id": ...}) — params are the 2nd positional arg.
        params = db.execute.call_args.args[1]
        assert params == {"tenant_id": 2}
        assert isinstance(params["tenant_id"], int)
