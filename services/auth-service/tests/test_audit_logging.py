"""Audit log write path in auth-service: messages, write points, failure isolation.

Services run with a real ``AuditLogWriter`` on a fake ai4iplatform_core
session, so the rows asserted on are exactly what would be inserted.
"""

import base64
import logging
import os
from contextlib import asynccontextmanager
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

_TEST_KEY = base64.b64encode(b"\x01" * 64).decode("ascii")
os.environ.setdefault("PII_ENCRYPTION_KEY", _TEST_KEY)

from ai4i_core.audit import AuditEntity, AuditLog, AuditLogWriter, AuditTrace  # noqa: E402
from ai4i_core.audit.snapshot import get_audit_model  # noqa: E402
from ai4i_core.context import reset_trace_id, set_trace_id  # noqa: E402

from app.core import pii_crypto  # noqa: E402
from app.core.exceptions import ServiceUnavailableError, ValidationError  # noqa: E402
from app.dependencies.services import get_audit_log_repository  # noqa: E402
from app.models.tenant import Tenant, TenantStatus  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routes.audit_logs import list_audit_logs  # noqa: E402
from app.schemas.tenant import TenantStatusUpdate  # noqa: E402
from app.services import audit_messages as am  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.tenant_service import TenantService  # noqa: E402

pii_crypto.configure_key(_TEST_KEY)


def _enc_email(value: str) -> str:
    return pii_crypto.encrypt(value, pii_crypto.EMAIL_CONTEXT)


# ── Fixtures ────────────────────────────────────────────────────────────


class _Tasks:
    """Stand-in for the request's FastAPI BackgroundTasks."""

    def __init__(self) -> None:
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))

    async def run(self) -> None:
        for func, args in self.tasks:
            await func(*args)


def _factory():
    """ai4iplatform_core session factory; ``factory.session`` records rows."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def make():
        yield session

    make.session = session
    return make


def _rows(factory) -> list[AuditLog]:
    return [c.args[0] for c in factory.session.add.call_args_list]


def _auth_db(tenant: Tenant) -> MagicMock:
    """ai4iplatform_auth session: answers track()'s SELECT from ``tenant``."""
    db = MagicMock()

    async def execute(stmt):
        names = [c.name for c in stmt.selected_columns]
        result = MagicMock()
        result.mappings.return_value.first.return_value = {
            n: getattr(tenant, n) for n in names
        }
        return result

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _apply(obj, data: dict):
    for key, value in data.items():
        setattr(obj, key, value)
    return obj


def _service(tenant: Tenant, factory=None, tasks=None) -> TenantService:
    user_repo = MagicMock()
    user_repo.lock_tenant_users_for_status = AsyncMock()
    user_repo.unlock_tenant_users_for_status = AsyncMock()
    user_repo.update = AsyncMock(side_effect=_apply)
    user_repo.save_and_refresh = AsyncMock()
    user_repo.commit = AsyncMock()
    tenant_repo = MagicMock()
    tenant_repo._db = _auth_db(tenant)
    tenant_repo.get_by_id_for_update = AsyncMock(return_value=tenant)
    tenant_repo.update = AsyncMock(side_effect=_apply)
    tenant_repo.save_and_refresh = AsyncMock()
    tenant_repo.commit = AsyncMock()
    tenant_repo.refresh = AsyncMock()
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=["ADMIN"])  # caller is ADMIN
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
        api_key_service=AsyncMock(),
        audit=AuditLogWriter(factory or _factory(), background_tasks=tasks or _Tasks()),
    )


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


_TIME = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC"


# ── Message templates ───────────────────────────────────────────────────


class TestTenantStatusTemplate:
    def test_suspend(self) -> None:
        assert am.tenant_status_template("ACTIVE", "SUSPENDED") == "Tenant '{organisation}' suspended"

    def test_deactivate_and_activate(self) -> None:
        assert am.tenant_status_template(TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED) == (
            "Tenant '{organisation}' deactivated"
        )
        assert am.tenant_status_template("DEACTIVATED", "ACTIVE") == "Tenant '{organisation}' activated"

    def test_setup_completed(self) -> None:
        assert am.tenant_status_template("PENDING", "ACTIVE") == (
            "Tenant '{organisation}' activated after the contact admin completed setup"
        )

    def test_who_when_and_reason_are_left_to_the_library(self) -> None:
        template = am.tenant_status_template("ACTIVE", "SUSPENDED")
        for placeholder in ("{performed_by}", "{at}", "{reason}"):
            assert placeholder not in template

    def test_tenant_model_is_registered(self) -> None:
        assert get_audit_model(AuditEntity.TENANT) is Tenant


# ── Tenant status change ────────────────────────────────────────────────


class TestTenantStatusChangeAudit:
    @pytest.mark.asyncio
    async def test_suspend_writes_row_after_response(self) -> None:
        factory, tasks = _factory(), _Tasks()
        svc = _service(_tenant(), factory, tasks)
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

        # Scheduled, not yet written: the insert runs after the response.
        assert len(tasks.tasks) == 1
        assert _rows(factory) == []
        await tasks.run()

        (row,) = _rows(factory)
        assert (row.entity_name, row.entity_id, row.action) == ("TENANT", "7", "STATUS_CHANGE")
        assert row.performed_by == admin.id
        assert row.trace_id == "trace-suspend"
        assert row.previous_state == {
            "organisation": "Acme University", "status": "ACTIVE", "reason": None,
        }
        assert row.new_state == {
            "organisation": "Acme University", "status": "SUSPENDED",
            "reason": "Agreement renewal pending",
        }
        assert re.fullmatch(
            rf"Tenant 'Acme University' suspended by {admin.id} on {_TIME}\. "
            r"Reason: Agreement renewal pending\.",
            row.message,
        )
        # The time in the message is the row's created_at.
        assert row.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") in row.message
        # Only the tracked properties are stored: no PII.
        assert "email" not in row.new_state

    @pytest.mark.asyncio
    async def test_old_values_read_before_change_and_logged_after_commit(self) -> None:
        tasks = _Tasks()
        svc = _service(_tenant(), tasks=tasks)
        order: list[str] = []
        read = svc._tenants._db.execute.side_effect

        async def track_read(stmt):
            order.append("track")
            return await read(stmt)

        async def update(obj, data):
            order.append("update")
            return await _apply(obj, data)

        svc._tenants._db.execute.side_effect = track_read
        svc._tenants.update.side_effect = update
        svc._tenants.save_and_refresh.side_effect = lambda *_: order.append("commit")
        real_add = tasks.add_task
        tasks.add_task = lambda *a: order.append("log") or real_add(*a)

        await svc.update_tenant_status(
            _admin(), 7, TenantStatusUpdate(status=TenantStatus.SUSPENDED, reason="R")
        )
        assert order == ["track", "update", "commit", "log"]

    @pytest.mark.asyncio
    async def test_reactivation_row_stores_description_as_reason(self) -> None:
        factory, tasks = _factory(), _Tasks()
        svc = _service(_tenant(TenantStatus.DEACTIVATED, reason="Merged"), factory, tasks)

        await svc.update_tenant_status(
            _admin(), 7, TenantStatusUpdate(status=TenantStatus.ACTIVE, reason="New agreement")
        )
        await tasks.run()

        (row,) = _rows(factory)
        assert row.previous_state["reason"] == "Merged"
        assert row.new_state["reason"] == "New agreement"
        assert row.message.endswith("Reason: New agreement.")

    @pytest.mark.asyncio
    async def test_audit_insert_failure_keeps_entity_change(self, caplog) -> None:
        factory, tasks = _factory(), _Tasks()
        factory.session.commit.side_effect = RuntimeError("platform-core unavailable")
        tenant = _tenant()
        svc = _service(tenant, factory, tasks)
        token = set_trace_id("trace-fail")
        try:
            result = await svc.update_tenant_status(
                _admin(), 7, TenantStatusUpdate(status=TenantStatus.SUSPENDED, reason="R")
            )
        finally:
            reset_trace_id(token)
        with caplog.at_level(logging.ERROR, logger="ai4i_core.audit.writer"):
            await tasks.run()  # must not raise

        assert result is tenant
        assert tenant.status == TenantStatus.SUSPENDED
        svc._tenants.save_and_refresh.assert_awaited_once_with(tenant)
        svc._api_keys.evict_keys_for_tenant.assert_awaited_once_with(7)
        errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
        assert any("trace_id=trace-fail" in m and "platform-core unavailable" in m for m in errors)

    @pytest.mark.asyncio
    async def test_track_read_failure_does_not_break_status_change(self) -> None:
        tasks = _Tasks()
        tenant = _tenant()
        svc = _service(tenant, tasks=tasks)
        svc._tenants._db.execute.side_effect = RuntimeError("select failed")

        result = await svc.update_tenant_status(
            _admin(), 7, TenantStatusUpdate(status=TenantStatus.SUSPENDED, reason="R")
        )
        assert result.status == TenantStatus.SUSPENDED
        assert tasks.tasks == []

    @pytest.mark.asyncio
    async def test_entity_commit_failure_logs_nothing(self) -> None:
        tasks = _Tasks()
        svc = _service(_tenant(), tasks=tasks)
        svc._tenants.save_and_refresh.side_effect = RuntimeError("auth db down")

        with pytest.raises(RuntimeError):
            await svc.update_tenant_status(
                _admin(), 7, TenantStatusUpdate(status=TenantStatus.SUSPENDED, reason="R")
            )
        assert tasks.tasks == []


class TestContactAdminActivationAudit:
    @pytest.mark.asyncio
    async def test_setup_completed_row(self) -> None:
        factory, tasks = _factory(), _Tasks()
        svc = AuthService.__new__(AuthService)
        svc._audit = AuditLogWriter(factory, background_tasks=tasks)
        user = User(id=uuid4(), email="c@acme.edu", username="c", tenant_id=7)
        trace = AuditTrace(
            AuditEntity.TENANT, "7", am.TENANT_STATUS_AUDIT_PROPERTIES,
            {"organisation": "Acme", "status": "PENDING", "reason": None},
        )

        svc._log_contact_admin_activation(trace, user)
        await tasks.run()

        (row,) = _rows(factory)
        assert row.new_state["status"] == "ACTIVE"
        assert row.performed_by == user.id
        assert re.fullmatch(
            rf"Tenant 'Acme' activated after the contact admin completed setup by {user.id} on {_TIME}\.",
            row.message,
        )

    def test_no_trace_logs_nothing(self) -> None:
        tasks = _Tasks()
        svc = AuthService.__new__(AuthService)
        svc._audit = AuditLogWriter(_factory(), background_tasks=tasks)
        svc._log_contact_admin_activation(None, MagicMock())
        assert tasks.tasks == []


# ── Read API: GET /audit-logs ──────────────────────────────────────


def _row(**overrides) -> AuditLog:
    values = dict(
        id=5,
        created_at=datetime(2026, 11, 3, 10, 15, 31, tzinfo=timezone.utc),
        entity_name="TENANT",
        entity_id="7",
        action="STATUS_CHANGE",
        previous_state={"status": "ACTIVE", "reason": None, "email": _enc_email("asha@acme.edu")},
        new_state={"status": "SUSPENDED", "reason": "Agreement renewal pending", "email": _enc_email("asha@acme.edu")},
        message="Tenant 'Acme' suspended. Reason: Agreement renewal pending.",
        performed_by=uuid4(),
        trace_id="abc",
    )
    values.update(overrides)
    return AuditLog(**values)


async def _list(repo, **params):
    query = dict(
        entity_name=None, entity_id=None, action=None,
        from_=None, to=None, offset=0, limit=100,
    )
    query.update(params)
    return await list_audit_logs(**query, _user_id=uuid4(), repo=repo)


class TestListAuditLogs:
    @pytest.mark.asyncio
    async def test_returns_message_actor_and_time(self) -> None:
        row = _row()
        repo = MagicMock()
        repo.list = AsyncMock(return_value=[row])

        response = await _list(repo, entity_name=AuditEntity.TENANT, entity_id="7")

        repo.list.assert_awaited_once_with(
            AuditEntity.TENANT, "7", None, None, None, 0, 100
        )
        item = response.model_dump(by_alias=True)["data"][0]
        assert item["message"] == "Tenant 'Acme' suspended. Reason: Agreement renewal pending."
        assert item["performed_by"] == row.performed_by
        assert item["created_at"] == row.created_at
        assert item["previous_state"]["status"] == "ACTIVE"
        assert item["previous_state"]["reason"] is None
        assert item["new_state"]["status"] == "SUSPENDED"
        assert item["new_state"]["reason"] == "Agreement renewal pending"

    @pytest.mark.asyncio
    async def test_states_show_masked_email_not_ciphertext(self) -> None:
        repo = MagicMock()
        repo.list = AsyncMock(return_value=[_row()])
        item = (await _list(repo)).data[0]
        for state in (item.previous_state, item.new_state):
            assert not state["email"].startswith("enc:")
            assert "asha@acme.edu" != state["email"]
            assert "***" in state["email"]

    @pytest.mark.asyncio
    async def test_entity_id_without_entity_name_is_422(self) -> None:
        repo = MagicMock()
        repo.list = AsyncMock()
        with pytest.raises(ValidationError) as exc:
            await _list(repo, entity_id="7")
        assert exc.value.code == "INVALID_AUDIT_FILTER"
        repo.list.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_from_after_to_is_422(self) -> None:
        repo = MagicMock()
        repo.list = AsyncMock()
        with pytest.raises(ValidationError) as exc:
            await _list(
                repo,
                from_=datetime(2026, 11, 2, tzinfo=timezone.utc),
                to=datetime(2026, 11, 1, tzinfo=timezone.utc),
            )
        assert exc.value.code == "INVALID_AUDIT_FILTER"

    def test_repository_dependency_is_503_without_platform_core_db(self) -> None:
        with pytest.raises(ServiceUnavailableError):
            get_audit_log_repository(platform_core_db=None)
