"""ai4i_core.audit: snapshot(), diff(), AuditLogWriter, AuditLogRepository."""

import enum
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Column, Date, DateTime, Enum, Integer, Numeric, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import Text, TypeDecorator

from ai4i_core.audit import (
    AuditAction,
    AuditEntity,
    AuditLog,
    AuditLogRepository,
    AuditLogWriter,
    diff,
    snapshot,
)
from ai4i_core.context import reset_trace_id, set_trace_id

Base = declarative_base()


class Colour(str, enum.Enum):
    RED = "RED"
    BLUE = "BLUE"


class Reversed(TypeDecorator):
    """Stand-in for an encrypted column: the stored form differs from the value."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else "enc:" + value[::-1]

    def process_result_value(self, value, dialect):
        return None if value is None else value[4:][::-1]


class Widget(Base):
    __tablename__ = "widgets"

    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    secret = Column(Reversed())
    owner = Column(PG_UUID(as_uuid=True))
    budget = Column(Numeric(15, 2))
    starts = Column(DateTime(timezone=True))
    day = Column(Date)
    colour = Column(Enum(Colour))
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    created_by = Column(PG_UUID(as_uuid=True))
    updated_by = Column(PG_UUID(as_uuid=True))


OWNER = uuid.UUID("3f2a0000-0000-0000-0000-000000000001")


def _widget(**overrides) -> Widget:
    values = dict(
        id=7,
        name="Acme",
        secret="hello",
        owner=OWNER,
        budget=Decimal("1000.50"),
        starts=datetime(2026, 11, 1, 10, 30, tzinfo=timezone.utc),
        day=date(2026, 11, 2),
        colour=Colour.RED,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        created_by=uuid.uuid4(),
        updated_by=uuid.uuid4(),
    )
    values.update(overrides)
    return Widget(**values)


def _session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _added_rows(session: MagicMock) -> list[AuditLog]:
    return [c.args[0] for c in session.add.call_args_list]


# ── snapshot() ──────────────────────────────────────────────────────────


class TestSnapshot:
    def test_column_values_are_json_native(self) -> None:
        snap = snapshot(AuditEntity.TENANT, _widget())
        assert snap == {
            "id": 7,
            "name": "Acme",
            "secret": "enc:olleh",
            "owner": str(OWNER),
            "budget": "1000.50",
            "starts": "2026-11-01T10:30:00+00:00",
            "day": "2026-11-02",
            "colour": "RED",
        }

    def test_bookkeeping_columns_excluded(self) -> None:
        snap = snapshot(AuditEntity.TENANT, _widget())
        for key in ("created_at", "updated_at", "created_by", "updated_by"):
            assert key not in snap

    def test_type_decorator_column_stored_in_bound_form(self) -> None:
        # Encrypted PII columns land as ciphertext, never as the plaintext value.
        snap = snapshot(AuditEntity.TENANT, _widget(secret="a@b.com"))
        assert snap["secret"] == "enc:moc.b@a"
        assert "a@b.com" not in str(snap)

    def test_unloaded_attributes_are_skipped_not_loaded(self) -> None:
        # A pending object has only the attributes that were set.
        snap = snapshot(AuditEntity.TENANT, Widget(id=1, name="x"))
        assert snap == {"id": 1, "name": "x"}

    def test_extra_is_merged_and_normalised(self) -> None:
        snap = snapshot(AuditEntity.TENANT_USER, Widget(id=1), extra={"roles": ("A", "B")})
        assert snap == {"id": 1, "roles": ["A", "B"]}

    def test_tenant_user_rule_excludes_last_login(self) -> None:
        snap = snapshot(AuditEntity.TENANT_USER, {"id": 1, "last_login": "x", "name": "n"})
        assert snap == {"id": 1, "name": "n"}

    def test_equal_objects_give_equal_snapshots(self) -> None:
        assert snapshot(AuditEntity.TENANT, _widget()) == snapshot(AuditEntity.TENANT, _widget())


# ── diff() ──────────────────────────────────────────────────────────────


class TestDiff:
    def test_changed_fields_only_sorted(self) -> None:
        prev = {"status": "ACTIVE", "name": "A", "reason": None}
        new = {"status": "SUSPENDED", "name": "A", "reason": "Agreement renewal pending"}
        assert diff(prev, new) == [
            {"field": "reason", "from": None, "to": "Agreement renewal pending"},
            {"field": "status", "from": "ACTIVE", "to": "SUSPENDED"},
        ]

    def test_create_lists_every_populated_field_from_none(self) -> None:
        assert diff(None, {"name": "A", "id": 1, "phone": None}) == [
            {"field": "id", "from": None, "to": 1},
            {"field": "name", "from": None, "to": "A"},
        ]

    def test_soft_delete(self) -> None:
        prev = {"is_delete": False, "is_active": True, "username": "u"}
        new = {"is_delete": True, "is_active": False, "username": "del_1"}
        assert [c["field"] for c in diff(prev, new)] == ["is_active", "is_delete", "username"]
        assert diff(prev, new)[1] == {"field": "is_delete", "from": False, "to": True}

    def test_missing_key_counts_as_none(self) -> None:
        assert diff({"a": 1}, {}) == [{"field": "a", "from": 1, "to": None}]

    def test_identical_is_empty(self) -> None:
        assert diff({"a": 1}, {"a": 1}) == []
        assert diff(None, None) == []


# ── AuditLogWriter.track() ──────────────────────────────────────────────


class TestTrack:
    @pytest.mark.asyncio
    async def test_change_writes_one_row(self) -> None:
        session = _session()
        writer = AuditLogWriter(session)
        widget = _widget()
        actor = uuid.uuid4()
        token = set_trace_id("trace-123")
        try:
            async with writer.track(
                AuditEntity.TENANT, widget, AuditAction.STATUS_CHANGE, performed_by=actor
            ) as t:
                widget.colour = Colour.BLUE
                t.message = "changed"
        finally:
            reset_trace_id(token)

        (row,) = _added_rows(session)
        assert row.entity_name == "TENANT"
        assert row.entity_id == "7"
        assert row.action == "STATUS_CHANGE"
        assert row.previous_state["colour"] == "RED"
        assert row.new_state["colour"] == "BLUE"
        assert row.message == "changed"
        assert row.performed_by == actor
        assert row.trace_id == "trace-123"
        session.flush.assert_awaited_once()
        session.commit.assert_not_awaited()  # the caller commits

    @pytest.mark.asyncio
    async def test_no_change_writes_nothing(self) -> None:
        session = _session()
        widget = _widget()
        async with AuditLogWriter(session).track(AuditEntity.TENANT, widget, AuditAction.UPDATE):
            widget.name = "Acme"  # same value
        session.add.assert_not_called()
        session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bookkeeping_only_change_writes_nothing(self) -> None:
        session = _session()
        widget = _widget()
        async with AuditLogWriter(session).track(AuditEntity.TENANT, widget, AuditAction.UPDATE):
            widget.updated_by = uuid.uuid4()
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_has_no_previous_state(self) -> None:
        session = _session()
        widget = Widget(name="New")
        async with AuditLogWriter(session).track(AuditEntity.TENANT, widget, AuditAction.CREATE) as t:
            assert t.before is None
            widget.id = 9  # stands in for the id assigned at flush
            assert t.after_now() == {"id": 9, "name": "New"}
        (row,) = _added_rows(session)
        assert row.previous_state is None
        assert row.new_state == {"id": 9, "name": "New"}
        assert row.entity_id == "9"

    @pytest.mark.asyncio
    async def test_exception_in_block_writes_nothing(self) -> None:
        session = _session()
        widget = _widget()
        with pytest.raises(RuntimeError):
            async with AuditLogWriter(session).track(AuditEntity.TENANT, widget, AuditAction.UPDATE):
                widget.name = "Changed"
                raise RuntimeError("entity write failed")
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_extra_loader_read_before_and_after(self) -> None:
        session = _session()
        roles = [["USER"], ["TENANT ADMIN"]]
        loader = AsyncMock(side_effect=lambda: {"roles": roles.pop(0)})
        widget = _widget()
        async with AuditLogWriter(session).track(
            AuditEntity.TENANT_USER, widget, AuditAction.UPDATE, extra=loader
        ):
            pass
        (row,) = _added_rows(session)
        assert diff(row.previous_state, row.new_state) == [
            {"field": "roles", "from": ["USER"], "to": ["TENANT ADMIN"]}
        ]

    @pytest.mark.asyncio
    async def test_rejects_non_enum_values(self) -> None:
        writer = AuditLogWriter(_session())
        with pytest.raises(TypeError):
            async with writer.track("TENANT", _widget(), AuditAction.UPDATE):
                pass
        with pytest.raises(TypeError):
            async with writer.track(AuditEntity.TENANT, _widget(), "UPDATE"):
                pass

    @pytest.mark.asyncio
    async def test_no_session_runs_block_and_records_nothing(self, caplog) -> None:
        widget = _widget()
        with caplog.at_level(logging.WARNING, logger="ai4i_core.audit.writer"):
            async with AuditLogWriter(None).track(AuditEntity.TENANT, widget, AuditAction.UPDATE):
                widget.name = "Changed"
        assert widget.name == "Changed"
        assert "not configured" in caplog.text
        assert await AuditLogWriter(None).commit() is False

    @pytest.mark.asyncio
    async def test_isolated_flush_failure_is_logged_not_raised(self, caplog) -> None:
        session = _session()
        session.flush.side_effect = RuntimeError("db down")
        widget = _widget()
        token = set_trace_id("trace-flush")
        try:
            with caplog.at_level(logging.ERROR, logger="ai4i_core.audit.writer"):
                async with AuditLogWriter(session).track(
                    AuditEntity.TENANT, widget, AuditAction.UPDATE
                ):
                    widget.name = "Changed"
        finally:
            reset_trace_id(token)
        assert "trace_id=trace-flush" in caplog.text
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shared_session_flush_failure_propagates(self) -> None:
        session = _session()
        session.flush.side_effect = RuntimeError("db down")
        widget = _widget()
        with pytest.raises(RuntimeError):
            async with AuditLogWriter(session, isolated=False).track(
                AuditEntity.TENANT, widget, AuditAction.UPDATE
            ):
                widget.name = "Changed"


# ── AuditLogWriter.commit() ─────────────────────────────────────────────


class TestCommit:
    @pytest.mark.asyncio
    async def test_commit_commits_session(self) -> None:
        session = _session()
        assert await AuditLogWriter(session).commit() is True
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_failure_logs_error_with_trace_id_and_does_not_raise(self, caplog) -> None:
        session = _session()
        session.commit.side_effect = RuntimeError("connection reset")
        token = set_trace_id("trace-abc")
        try:
            with caplog.at_level(logging.ERROR, logger="ai4i_core.audit.writer"):
                assert await AuditLogWriter(session).commit() is False
        finally:
            reset_trace_id(token)
        record = next(r for r in caplog.records if r.levelno == logging.ERROR)
        assert "trace_id=trace-abc" in record.getMessage()
        assert "connection reset" in record.getMessage()
        session.rollback.assert_awaited_once()


# ── AuditLogRepository ──────────────────────────────────────────────────


class TestRepository:
    async def _sql(self, **filters) -> str:
        session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        await AuditLogRepository(session).list(**filters)
        stmt = session.execute.await_args.args[0]
        return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    @pytest.mark.asyncio
    async def test_all_filters_ordering_and_paging(self) -> None:
        sql = await self._sql(
            entity_name=AuditEntity.TENANT,
            entity_id="7",
            action=AuditAction.STATUS_CHANGE,
            from_=datetime(2026, 10, 1, tzinfo=timezone.utc),
            to_=datetime(2026, 11, 1, tzinfo=timezone.utc),
            offset=100,
            limit=50,
        )
        assert "audit_logs.entity_name = 'TENANT'" in sql
        assert "audit_logs.entity_id = '7'" in sql
        assert "audit_logs.action = 'STATUS_CHANGE'" in sql
        assert "audit_logs.created_at >= '2026-10-01" in sql
        assert "audit_logs.created_at < '2026-11-01" in sql
        assert "ORDER BY audit_logs.created_at DESC, audit_logs.id DESC" in sql
        assert "LIMIT 50" in sql and "OFFSET 100" in sql

    @pytest.mark.asyncio
    async def test_no_filters(self) -> None:
        sql = await self._sql()
        assert "WHERE" not in sql
        assert "LIMIT 100" in sql
