"""TenantService.create_tenant — validates budget_effective_from/_to the
same way revise_tenant_budget validates a fresh window.

Before this, TenantCreate accepted both dates as Optional[datetime] = None
with no validator, and create_tenant wrote them straight through
unvalidated. That was harmless while these columns were inert display
data, but this feature made them an enforcement gate: create_api_key 422s
BUDGET_EXPIRED for a tenant whose window has already lapsed, and
/auth/validate 403s any of its keys. So an operator creating a tenant with
an already-past budget_effective_to (or an inverted window, To before
From) got a tenant that was dead on arrival, with nothing at creation time
explaining why. This closes that gap by reusing the exact same validation
functions (and error codes) revise_tenant_budget already uses.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.services.tenant_service import TenantService

_VALID_FROM = datetime.now(timezone.utc)
_VALID_TO = _VALID_FROM + timedelta(days=30)


def _svc() -> TenantService:
    tenant_repo = AsyncMock()
    tenant_repo.get_by_email = AsyncMock(return_value=None)
    tenant_repo.get_by_organisation = AsyncMock(return_value=None)
    tenant_repo.create = AsyncMock()
    tenant_repo.refresh = AsyncMock()
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=AsyncMock(),
        role_service=AsyncMock(),
        verification_repo=AsyncMock(),
        credentials_repo=AsyncMock(),
        token_service=AsyncMock(),
        email_client=AsyncMock(),
    )


def _body(*, budget_effective_from=None, budget_effective_to=None) -> MagicMock:
    body = MagicMock()
    body.email = "contact@example.invalid"
    body.organisation = "Acme Corp"
    body.contact_name = "Jane Doe"
    body.phone_number = "+919876543210"
    body.plan_id = None
    body.tier_id = None
    body.allocated_budget = None
    body.budget_effective_from = budget_effective_from
    body.budget_effective_to = budget_effective_to
    return body


def _current_user() -> User:
    return User(id=uuid4(), email="admin@example.invalid", username="admin")


class TestCreateTenantEffectiveWindowValidation:
    @pytest.mark.asyncio
    async def test_both_omitted_is_allowed(self) -> None:
        """No window assigned at creation — unchanged, existing behavior."""
        svc = _svc()
        svc.provision_user = AsyncMock()
        svc._allocate_unique_username = AsyncMock(return_value="jane.doe")

        await svc.create_tenant(_body(), _current_user(), MagicMock())

        svc._tenants.create.assert_awaited_once()
        tenant = svc._tenants.create.await_args.args[0]
        assert tenant.budget_effective_from is None
        assert tenant.budget_effective_to is None

    @pytest.mark.asyncio
    async def test_both_given_and_valid_is_allowed(self) -> None:
        svc = _svc()
        svc.provision_user = AsyncMock()
        svc._allocate_unique_username = AsyncMock(return_value="jane.doe")

        await svc.create_tenant(
            _body(budget_effective_from=_VALID_FROM, budget_effective_to=_VALID_TO),
            _current_user(),
            MagicMock(),
        )

        svc._tenants.create.assert_awaited_once()
        tenant = svc._tenants.create.await_args.args[0]
        assert tenant.budget_effective_from == _VALID_FROM
        assert tenant.budget_effective_to == _VALID_TO

    @pytest.mark.asyncio
    async def test_only_from_given_is_rejected(self) -> None:
        svc = _svc()

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant(
                _body(budget_effective_from=_VALID_FROM), _current_user(), MagicMock()
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "effective_window_required"
        svc._tenants.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_only_to_given_is_rejected(self) -> None:
        svc = _svc()

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant(
                _body(budget_effective_to=_VALID_TO), _current_user(), MagicMock()
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "effective_window_required"
        svc._tenants.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_backdated_from_is_rejected(self) -> None:
        """The exact bug scenario: an operator creates a tenant with an
        already-past budget_effective_to — before this fix, nothing
        stopped it, and the tenant would be dead on arrival (every
        create_api_key call for them 422s BUDGET_EXPIRED with no obvious
        cause)."""
        yesterday = _VALID_FROM - timedelta(days=1)

        svc = _svc()

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant(
                _body(budget_effective_from=yesterday, budget_effective_to=_VALID_TO),
                _current_user(),
                MagicMock(),
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_effective_from_invalid"
        svc._tenants.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inverted_window_is_rejected(self) -> None:
        """To before From — a nonsensical window that revise_tenant_budget
        already rejects; create_tenant must reject it identically."""
        svc = _svc()

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant(
                _body(budget_effective_from=_VALID_TO, budget_effective_to=_VALID_FROM),
                _current_user(),
                MagicMock(),
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_effective_to_invalid"
        svc._tenants.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_same_day_window_is_rejected(self) -> None:
        same_day_to = _VALID_FROM.replace(hour=23, minute=59)
        svc = _svc()

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant(
                _body(budget_effective_from=_VALID_FROM, budget_effective_to=same_day_to),
                _current_user(),
                MagicMock(),
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "budget_effective_to_invalid"

    @pytest.mark.asyncio
    async def test_window_validation_runs_before_duplicate_checks_are_reached_only_after_them(
        self,
    ) -> None:
        """Duplicate email/organisation are still checked first (existing
        behavior, unchanged) — the window check sits after them, not
        before, so a genuinely duplicate tenant still 409s rather than
        exposing the window violation first."""
        svc = _svc()
        svc._tenants.get_by_email = AsyncMock(return_value=object())

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_tenant(
                _body(budget_effective_from=_VALID_FROM), _current_user(), MagicMock()
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_TENANT_EMAIL"
