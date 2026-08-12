"""Unit tests for tenant_assignment_service.reassign_tier.

All DB I/O (both the primary session and the auth-DB session) is mocked via
AsyncMock; no running services or databases required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.pay_per_use.tenant_assignment import TierAssignRequest, TierReassignRequest
from app.services.pay_per_use import tenant_assignment_service as svc


def _exec_result(scalar_one_or_none=None, scalars_first=None):
    """Build a mock SQLAlchemy execute() result supporting the accessor the
    caller happens to use (scalar_one_or_none() or scalars().first())."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar_one_or_none)
    scalars_mock = MagicMock()
    scalars_mock.first = MagicMock(return_value=scalars_first)
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


async def _fake_refresh(obj):
    """Simulate the DB populating server_default columns on refresh()."""
    if getattr(obj, "updated_at", None) is None:
        obj.updated_at = datetime.now(timezone.utc)


def _make_db(execute_results):
    """AsyncSession stand-in whose .execute() yields results in order."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_results)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=_fake_refresh)
    return db


def _make_auth_db(tenant_row):
    auth_db = MagicMock()
    row_result = MagicMock()
    row_result.first = MagicMock(return_value=tenant_row)
    auth_db.execute = AsyncMock(return_value=row_result)
    return auth_db


def _tenant_row(status="ACTIVE"):
    return SimpleNamespace(id=1, name="Acme", status=status)


def _tier(name="gold"):
    return SimpleNamespace(id=uuid4(), name=name, is_active=True)


def _assignment(tier_id, budget=Decimal("100"), balance=Decimal("40"),
                 effective_from=None, effective_to=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        tenant_id="1",
        tier_id=tier_id,
        budget_limit=budget,
        available_balance=balance,
        effective_from=effective_from or (now - timedelta(days=1)),
        effective_to=effective_to or (now + timedelta(days=30)),
        updated_by=None,
        updated_at=now,
    )


@pytest.mark.asyncio
class TestReassignTier:
    async def test_happy_path_reassigns_and_carries_over_balance(self):
        old_tier_id, new_tier = uuid4(), _tier("platinum")
        current = _assignment(tier_id=old_tier_id)
        db = _make_db([
            _exec_result(scalar_one_or_none=new_tier),   # tier lookup
            _exec_result(scalar_one_or_none=current),    # current active assignment
            _exec_result(scalars_first=None),            # no overlap
        ])
        auth_db = _make_auth_db(_tenant_row("ACTIVE"))

        result = await svc.reassign_tier(
            TierReassignRequest(tenant_id="1", tier_id=str(new_tier.id)),
            db, auth_db, user_id="admin",
        )

        assert result.tier_id == str(new_tier.id)
        assert result.budget_limit == current.budget_limit
        assert result.available_balance == current.available_balance
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    async def test_inactive_tenant_is_rejected_before_any_tier_lookup(self):
        db = _make_db([])  # reassign_tier must fail before touching db.execute
        auth_db = _make_auth_db(_tenant_row("SUSPENDED"))

        with pytest.raises(HTTPException) as exc:
            await svc.reassign_tier(
                TierReassignRequest(tenant_id="1", tier_id=str(uuid4())),
                db, auth_db, user_id="admin",
            )

        assert exc.value.status_code == 422
        db.execute.assert_not_awaited()

    async def test_unknown_tenant_is_rejected(self):
        db = _make_db([])
        auth_db = _make_auth_db(None)

        with pytest.raises(HTTPException) as exc:
            await svc.reassign_tier(
                TierReassignRequest(tenant_id="999", tier_id=str(uuid4())),
                db, auth_db, user_id="admin",
            )

        assert exc.value.status_code == 404

    async def test_same_tier_reassignment_is_conflict(self):
        tier_id = uuid4()
        current = _assignment(tier_id=tier_id)
        same_tier = _tier()
        same_tier.id = tier_id
        db = _make_db([
            _exec_result(scalar_one_or_none=same_tier),
            _exec_result(scalar_one_or_none=current),
        ])
        auth_db = _make_auth_db(_tenant_row("ACTIVE"))

        with pytest.raises(HTTPException) as exc:
            await svc.reassign_tier(
                TierReassignRequest(tenant_id="1", tier_id=str(tier_id)),
                db, auth_db, user_id="admin",
            )

        assert exc.value.status_code == 409

    async def test_no_active_assignment_is_not_found(self):
        new_tier = _tier()
        db = _make_db([
            _exec_result(scalar_one_or_none=new_tier),
            _exec_result(scalar_one_or_none=None),  # no active assignment row
            _exec_result(scalar_one_or_none=None),  # _lock_active_assignment's built-in retry, also empty
        ])
        auth_db = _make_auth_db(_tenant_row("ACTIVE"))

        with pytest.raises(HTTPException) as exc:
            await svc.reassign_tier(
                TierReassignRequest(tenant_id="1", tier_id=str(new_tier.id)),
                db, auth_db, user_id="admin",
            )

        assert exc.value.status_code == 404

    async def test_future_dated_assignment_overlap_is_conflict(self):
        old_tier_id, new_tier = uuid4(), _tier()
        current = _assignment(tier_id=old_tier_id)
        future_assignment = _assignment(
            tier_id=uuid4(),
            effective_from=current.effective_to - timedelta(days=1),
            effective_to=current.effective_to + timedelta(days=30),
        )
        db = _make_db([
            _exec_result(scalar_one_or_none=new_tier),
            _exec_result(scalar_one_or_none=current),
            _exec_result(scalars_first=future_assignment),  # overlap found
        ])
        auth_db = _make_auth_db(_tenant_row("ACTIVE"))

        with pytest.raises(HTTPException) as exc:
            await svc.reassign_tier(
                TierReassignRequest(tenant_id="1", tier_id=str(new_tier.id)),
                db, auth_db, user_id="admin",
            )

        assert exc.value.status_code == 409
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    async def test_invalid_tier_id_format_is_bad_request(self):
        db = _make_db([])
        auth_db = _make_auth_db(_tenant_row("ACTIVE"))

        with pytest.raises(HTTPException) as exc:
            await svc.reassign_tier(
                TierReassignRequest(tenant_id="1", tier_id="not-a-uuid"),
                db, auth_db, user_id="admin",
            )

        assert exc.value.status_code == 400

    async def test_inactive_tier_is_not_found(self):
        db = _make_db([
            _exec_result(scalar_one_or_none=None),  # PPUTier.is_active == True filters it out
        ])
        auth_db = _make_auth_db(_tenant_row("ACTIVE"))

        with pytest.raises(HTTPException) as exc:
            await svc.reassign_tier(
                TierReassignRequest(tenant_id="1", tier_id=str(uuid4())),
                db, auth_db, user_id="admin",
            )

        assert exc.value.status_code == 404


class TestTierAssignRequestValidation:
    """AI4IDS-2216 / budget precision ticket: budget=0 must be rejected (422)."""

    def _kwargs(self, budget):
        now = datetime.now(timezone.utc)
        return dict(
            tenant_id="1",
            tier_id=str(uuid4()),
            budget=budget,
            effective_from=now,
            effective_to=now + timedelta(days=30),
        )

    def test_zero_budget_is_rejected(self):
        with pytest.raises(ValidationError):
            TierAssignRequest(**self._kwargs(Decimal("0")))

    def test_negative_budget_is_rejected(self):
        with pytest.raises(ValidationError):
            TierAssignRequest(**self._kwargs(Decimal("-1")))

    def test_positive_budget_is_accepted(self):
        request = TierAssignRequest(**self._kwargs(Decimal("100")))
        assert request.budget == Decimal("100")

    def test_naive_effective_from_is_rejected(self):
        kwargs = self._kwargs(Decimal("100"))
        kwargs["effective_from"] = datetime.now()
        with pytest.raises(ValidationError):
            TierAssignRequest(**kwargs)

    def test_naive_effective_to_is_rejected(self):
        kwargs = self._kwargs(Decimal("100"))
        kwargs["effective_to"] = datetime.now() + timedelta(days=30)
        with pytest.raises(ValidationError):
            TierAssignRequest(**kwargs)


@pytest.mark.asyncio
class TestAssignTierEffectiveFromValidation:
    """AI4IDS-2783: assign_tier must reject past dates but allow today, in UTC day terms."""

    def _request(self, effective_from):
        return TierAssignRequest(
            tenant_id="1",
            tier_id=str(uuid4()),
            budget=Decimal("100"),
            effective_from=effective_from,
            effective_to=effective_from + timedelta(days=30),
        )

    async def test_yesterday_is_rejected(self):
        db = _make_db([
            _exec_result(scalar_one_or_none=_tier()),
        ])
        auth_db = _make_auth_db(_tenant_row("ACTIVE"))
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)

        with pytest.raises(HTTPException) as exc:
            await svc.assign_tier(self._request(yesterday), db, auth_db, user_id="admin")

        assert exc.value.status_code == 422
        assert "past" in exc.value.detail

    async def test_today_start_of_day_is_accepted(self):
        tier = _tier()
        db = _make_db([
            _exec_result(scalar_one_or_none=tier),
            _exec_result(scalars_first=None),  # no overlap
        ])
        auth_db = _make_auth_db(_tenant_row("ACTIVE"))
        today_utc_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        result = await svc.assign_tier(
            self._request(today_utc_start), db, auth_db, user_id="admin"
        )

        assert result.tier_id == str(tier.id)
        db.add.assert_called_once()
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
class TestListTenantTiers:
    """AI4IDS-2506: filtering by a nonexistent tier_id must 404, not 200 + []."""

    async def test_nonexistent_tier_id_returns_404(self):
        db = _make_db([
            _exec_result(scalar_one_or_none=None),  # tier existence check misses
        ])

        with pytest.raises(HTTPException) as exc:
            await svc.list_tenant_tiers(db, tier_id=str(uuid4()))

        assert exc.value.status_code == 404

    async def test_existing_tier_with_no_assignments_returns_empty_list(self):
        tier_id = uuid4()
        assignments_result = MagicMock()
        assignments_result.all = MagicMock(return_value=[])
        db = _make_db([
            _exec_result(scalar_one_or_none=tier_id),  # tier exists
            assignments_result,  # join query — zero current assignments
        ])

        result = await svc.list_tenant_tiers(db, tier_id=str(tier_id))

        assert result == []

    async def test_invalid_uuid_format_returns_400(self):
        db = _make_db([])

        with pytest.raises(HTTPException) as exc:
            await svc.list_tenant_tiers(db, tier_id="not-a-uuid")

        assert exc.value.status_code == 400

    async def test_no_tier_id_filter_skips_existence_check(self):
        assignments_result = MagicMock()
        assignments_result.all = MagicMock(return_value=[])
        db = _make_db([assignments_result])

        result = await svc.list_tenant_tiers(db, tier_id=None)

        assert result == []
        assert db.execute.await_count == 1
