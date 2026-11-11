"""Audit log write path in auth-service: messages, write points, failure isolation.

Services run with a real ``AuditLogWriter`` on a fake ai4iplatform_core
session, so the rows asserted on are exactly what would be inserted.
"""

import base64
import logging
import os
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

_TEST_KEY = base64.b64encode(b"\x01" * 64).decode("ascii")
os.environ.setdefault("PII_ENCRYPTION_KEY", _TEST_KEY)

from ai4i_core.audit import AuditLog, AuditLogWriter, diff  # noqa: E402
from ai4i_core.context import reset_trace_id, set_trace_id  # noqa: E402

from app.core import pii_crypto  # noqa: E402
from app.models.tenant import Tenant, TenantStatus  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.tenant import TenantStatusUpdate  # noqa: E402
from app.services import audit_messages as am  # noqa: E402
from app.services.tenant_service import TenantService  # noqa: E402

pii_crypto.configure_key(_TEST_KEY)


def _enc_email(value: str) -> str:
    return pii_crypto.encrypt(value, pii_crypto.EMAIL_CONTEXT)


# ── Fixtures ────────────────────────────────────────────────────────────


def _audit_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _rows(session: MagicMock) -> list[AuditLog]:
    return [c.args[0] for c in session.add.call_args_list]


async def _apply(obj, data: dict):
    for key, value in data.items():
        setattr(obj, key, value)
    return obj


def _service(audit_session: MagicMock) -> TenantService:
    user_repo = MagicMock()
    user_repo.lock_tenant_users_for_status = AsyncMock()
    user_repo.unlock_tenant_users_for_status = AsyncMock()
    user_repo.update = AsyncMock(side_effect=_apply)
    user_repo.save_and_refresh = AsyncMock()
    user_repo.commit = AsyncMock()
    tenant_repo = MagicMock()
    tenant_repo.update = AsyncMock(side_effect=_apply)
    tenant_repo.save_and_refresh = AsyncMock()
    tenant_repo.commit = AsyncMock()
    tenant_repo.refresh = AsyncMock()
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=["ADMIN"])  # caller is ADMIN
    svc = TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
        api_key_service=AsyncMock(),
        audit=AuditLogWriter(audit_session),
    )
    return svc


def _tenant(status: TenantStatus = TenantStatus.ACTIVE, **kw) -> Tenant:
    values = dict(
        id=7,
        name="Asha Rao",
        organisation="Acme University",
        email="contact@acme.edu",
        phone_number="+919876543210",
        status=status,
    )
    values.update(kw)
    return Tenant(**values)


def _admin() -> User:
    return User(id=uuid4(), email="admin@example.invalid", username="admin", tenant_id=1)


# ── Messages ────────────────────────────────────────────────────────────


class TestTenantMessages:
    def test_suspend(self) -> None:
        message = am.tenant_status_changed(
            {"organisation": "Acme", "status": "ACTIVE"},
            {"organisation": "Acme", "status": "SUSPENDED", "reason": "Audit pending"},
        )
        assert message == "Tenant 'Acme' suspended."

    def test_deactivate(self) -> None:
        message = am.tenant_status_changed(
            {"organisation": "Acme", "status": "SUSPENDED"},
            {"organisation": "Acme", "status": "DEACTIVATED", "reason": "Agreement or engagement ended"},
        )
        assert message == "Tenant 'Acme' deactivated."

    def test_reactivate(self) -> None:
        message = am.tenant_status_changed(
            {"organisation": "Acme", "status": "DEACTIVATED"},
            {"organisation": "Acme", "status": "ACTIVE", "reason": "New agreement signed"},
        )
        assert message == "Tenant 'Acme' activated."

    def test_setup_completed(self) -> None:
        message = am.tenant_status_changed(
            {"organisation": "Acme", "status": "PENDING"},
            {"organisation": "Acme", "status": "ACTIVE"},
        )
        assert message == "Tenant 'Acme' activated. Contact admin completed setup."


# ── Tenant status change ────────────────────────────────────────────────


class TestTenantStatusChangeAudit:
    @pytest.mark.asyncio
    async def test_suspend_writes_status_change_row(self) -> None:
        session = _audit_session()
        svc = _service(session)
        tenant = _tenant()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        admin = _admin()
        token = set_trace_id("trace-suspend")
        try:
            await svc.update_tenant_status(
                admin,
                7,
                TenantStatusUpdate(status=TenantStatus.SUSPENDED, reason="Agreement renewal pending"),
            )
        finally:
            reset_trace_id(token)

        (row,) = _rows(session)
        assert (row.entity_name, row.entity_id, row.action) == ("TENANT", "7", "STATUS_CHANGE")
        assert row.performed_by == admin.id
        assert row.trace_id == "trace-suspend"
        assert diff(row.previous_state, row.new_state) == [
            {"field": "reason", "from": None, "to": "Agreement renewal pending"},
            {"field": "status", "from": "ACTIVE", "to": "SUSPENDED"},
        ]
        assert row.message == "Tenant 'Acme University' suspended."
        # The reason lives in the snapshot (design doc 2.2 / 8), not a column.
        assert row.new_state["reason"] == "Agreement renewal pending"
        # PII is stored as ciphertext, never plaintext.
        assert "contact@acme.edu" not in str(row.new_state)
        assert row.new_state["email"] == _enc_email("contact@acme.edu")
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_entity_commits_before_audit(self) -> None:
        session = _audit_session()
        svc = _service(session)
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        order: list[str] = []
        svc._tenants.save_and_refresh.side_effect = lambda *_: order.append("entity")
        session.commit.side_effect = lambda: order.append("audit")

        await svc.update_tenant_status(
            _admin(), 7, TenantStatusUpdate(status=TenantStatus.SUSPENDED, reason="R")
        )
        assert order == ["entity", "audit"]

    @pytest.mark.asyncio
    async def test_reactivation_row_stores_description_as_reason(self) -> None:
        session = _audit_session()
        svc = _service(session)
        tenant = _tenant(TenantStatus.DEACTIVATED, reason="Merged")
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)

        await svc.update_tenant_status(
            _admin(), 7, TenantStatusUpdate(status=TenantStatus.ACTIVE, reason="New agreement")
        )

        (row,) = _rows(session)
        assert row.previous_state["reason"] == "Merged"
        assert row.new_state["reason"] == "New agreement"

    @pytest.mark.asyncio
    async def test_audit_commit_failure_keeps_entity_change(self, caplog) -> None:
        session = _audit_session()
        session.commit.side_effect = RuntimeError("platform-core unavailable")
        svc = _service(session)
        tenant = _tenant()
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=tenant)
        token = set_trace_id("trace-fail")
        try:
            with caplog.at_level(logging.ERROR, logger="ai4i_core.audit.writer"):
                result = await svc.update_tenant_status(
                    _admin(), 7, TenantStatusUpdate(status=TenantStatus.SUSPENDED, reason="R")
                )
        finally:
            reset_trace_id(token)

        assert result is tenant
        assert tenant.status == TenantStatus.SUSPENDED
        svc._tenants.save_and_refresh.assert_awaited_once_with(tenant)
        svc._api_keys.evict_keys_for_tenant.assert_awaited_once_with(7)
        errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
        assert any("trace_id=trace-fail" in m and "platform-core unavailable" in m for m in errors)

    @pytest.mark.asyncio
    async def test_entity_commit_failure_never_commits_audit(self) -> None:
        session = _audit_session()
        svc = _service(session)
        svc._tenants.get_by_id_for_update = AsyncMock(return_value=_tenant())
        svc._tenants.save_and_refresh.side_effect = RuntimeError("auth db down")

        with pytest.raises(RuntimeError):
            await svc.update_tenant_status(
                _admin(), 7, TenantStatusUpdate(status=TenantStatus.SUSPENDED, reason="R")
            )
        session.commit.assert_not_awaited()
