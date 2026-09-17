"""scripts/backfill_tenant_budget_unset — closes the gap flagged in review on
the BUDGET_NOT_CONFIGURED fix: APIKeyService.set_tenant_budget_unset_for_tenant
is only ever invoked from TenantService.revise_tenant_budget, which by
definition always pushes False (a Budget was just assigned there). A key
issued under a tenant that has never been through a budget revision has no
tenant_budget_unset entry in its cached payload at all, and /auth/validate
reads that absence as "configured" — so those keys keep making real, billed
inference calls with zero enforcement. This script is the one-time fan-out
that finds every such tenant and pushes tenant_budget_unset=True onto its
already-issued keys, live.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.backfill_tenant_budget_unset import _run


def _tenant_row(tenant_id: int) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, i: tenant_id
    return row


@pytest.mark.asyncio
async def test_pushes_tenant_budget_unset_for_every_null_budget_tenant(monkeypatch) -> None:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(6,), (7,)]
    session.execute = AsyncMock(return_value=result)

    async def _fake_get_db():
        yield session

    monkeypatch.setattr("scripts.backfill_tenant_budget_unset.get_db", _fake_get_db)
    monkeypatch.setattr("scripts.backfill_tenant_budget_unset.get_redis_client", MagicMock())

    svc = AsyncMock()
    svc_cls = MagicMock(return_value=svc)
    monkeypatch.setattr("scripts.backfill_tenant_budget_unset.APIKeyService", svc_cls)

    count = await _run()

    assert count == 2
    assert svc.set_tenant_budget_unset_for_tenant.await_args_list == [
        ((6, True),),
        ((7, True),),
    ]


@pytest.mark.asyncio
async def test_no_null_budget_tenants_is_a_noop(monkeypatch) -> None:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    async def _fake_get_db():
        yield session

    monkeypatch.setattr("scripts.backfill_tenant_budget_unset.get_db", _fake_get_db)
    monkeypatch.setattr("scripts.backfill_tenant_budget_unset.get_redis_client", MagicMock())

    svc = AsyncMock()
    monkeypatch.setattr(
        "scripts.backfill_tenant_budget_unset.APIKeyService", MagicMock(return_value=svc)
    )

    count = await _run()

    assert count == 0
    svc.set_tenant_budget_unset_for_tenant.assert_not_awaited()
