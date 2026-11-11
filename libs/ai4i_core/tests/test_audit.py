"""ai4i_core.audit: entity registry, track() / log(), repository."""

import enum
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Column, Enum, Integer, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import Text, TypeDecorator

from ai4i_core.audit import (
    AuditAction,
    AuditEntity,
    AuditLog,
    AuditLogRepository,
    AuditLogWriter,
    AuditTrace,
    noop_audit_writer,
    register_audit_entity,
)
from ai4i_core.audit import snapshot as snapshot_module
from ai4i_core.audit.snapshot import snapshot_query, to_json_value
from ai4i_core.audit.writer import build_message
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
    status = Column(String(20))
    secret = Column(Reversed())
    colour = Column(Enum(Colour))


class Pair(Base):
    __tablename__ = "pairs"

    a = Column(Integer, primary_key=True)
    b = Column(Integer, primary_key=True)


PROPS = ("name", "status")
ACTOR = uuid.UUID("3f2a0000-0000-0000-0000-000000000001")


@pytest.fixture(autouse=True)
def _registry():
    saved = dict(snapshot_module._MODELS)
    snapshot_module._MODELS.clear()
    register_audit_entity(AuditEntity.TENANT, Widget)
    yield
    snapshot_module._MODELS.clear()
    snapshot_module._MODELS.update(saved)


def _db(row) -> MagicMock:
    """Entity session whose SELECT returns ``row`` (a dict or None)."""
    db = MagicMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    db.execute = AsyncMock(return_value=result)
    return db


def _factory():
    """Session factory recording added rows; ``factory.session`` is the mock."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def make():
        yield session

    make.session = session
    return make


class _Tasks:
    """Stand-in for FastAPI BackgroundTasks."""

    def __init__(self) -> None:
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))

    async def run(self) -> None:
        for func, args in self.tasks:
            await func(*args)


def _trace(before=None, **kw) -> AuditTrace:
    return AuditTrace(
        AuditEntity.TENANT, "7", PROPS,
        {"name": "Acme", "status": "ACTIVE"} if before is None else before, **kw,
    )


def _rows(factory) -> list[AuditLog]:
    return [c.args[0] for c in factory.session.add.call_args_list]


# ── registry / snapshot_query ───────────────────────────────────────────


class TestSnapshotQuery:
    def test_selects_only_the_properties_by_primary_key(self) -> None:
        sql = str(
            snapshot_query(Widget, 7, ["name", "status"]).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "SELECT widgets.name AS name, widgets.status AS status" in sql
        assert "WHERE widgets.id = 7" in sql
        assert "secret" not in sql

    def test_type_decorator_column_is_read_in_stored_form(self) -> None:
        stmt = snapshot_query(Widget, 7, ["secret"])
        column_type = stmt.selected_columns["secret"].type
        assert not isinstance(column_type, Reversed)
        assert isinstance(column_type, Text)

    def test_unknown_property_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            snapshot_query(Widget, 7, ["nope"])

    def test_composite_primary_key_cannot_be_registered(self) -> None:
        with pytest.raises(ValueError):
            register_audit_entity(AuditEntity.TENANT, Pair)


class TestToJsonValue:
    def test_values_are_json_native(self) -> None:
        assert to_json_value(Colour.RED) == "RED"
        assert type(to_json_value(Colour.RED)) is str  # str-based enum unwrapped
        assert to_json_value(ACTOR) == str(ACTOR)
        assert to_json_value(Decimal("1000.50")) == "1000.50"
        assert to_json_value(datetime(2026, 11, 1, 10, 30, tzinfo=timezone.utc)) == "2026-11-01T10:30:00+00:00"
        assert to_json_value(date(2026, 11, 2)) == "2026-11-02"
        assert to_json_value({"a": [Colour.BLUE]}) == {"a": ["BLUE"]}


# ── track() ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTrack:
    async def test_reads_old_values_from_db(self) -> None:
        db = _db({"name": "Acme", "status": Colour.RED})
        trace = await AuditLogWriter(None).track(db, AuditEntity.TENANT, 7, ["name", "status"])
        db.execute.assert_awaited_once()
        assert trace.before == {"name": "Acme", "status": "RED"}
        assert trace.entity_id == "7" and trace.enabled

    async def test_missing_row_gives_no_before(self) -> None:
        trace = await AuditLogWriter(None).track(_db(None), AuditEntity.TENANT, 7, PROPS)
        assert trace.before is None and trace.enabled

    async def test_unregistered_entity_disables_trace_without_query(self, caplog) -> None:
        snapshot_module._MODELS.clear()
        db = _db({})
        with caplog.at_level(logging.ERROR):
            trace = await AuditLogWriter(None).track(db, AuditEntity.TENANT, 7, PROPS)
        assert not trace.enabled
        db.execute.assert_not_awaited()
        assert "Audit track disabled" in caplog.text

    async def test_unknown_property_disables_trace(self) -> None:
        db = _db({})
        trace = await AuditLogWriter(None).track(db, AuditEntity.TENANT, 7, ["nope"])
        assert not trace.enabled
        db.execute.assert_not_awaited()

    async def test_db_error_disables_trace_and_does_not_raise(self, caplog) -> None:
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        with caplog.at_level(logging.ERROR):
            trace = await AuditLogWriter(None).track(db, AuditEntity.TENANT, 7, PROPS)
        assert not trace.enabled
        assert "db down" in caplog.text

    async def test_rejects_non_enum_entity(self) -> None:
        with pytest.raises(TypeError):
            await AuditLogWriter(None).track(_db({}), "TENANT", 7, PROPS)


# ── log() ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestLog:
    async def test_runs_in_background_and_writes_full_row(self) -> None:
        factory, tasks = _factory(), _Tasks()
        writer = AuditLogWriter(factory, background_tasks=tasks)
        token = set_trace_id("trace-1")
        try:
            writer.log(
                _trace(),
                AuditAction.STATUS_CHANGE,
                "Widget '{name}' {previous_status} -> {status}",
                {"status": "SUSPENDED"},
                performed_by=ACTOR,
            )
        finally:
            reset_trace_id(token)

        # Nothing written until the background task runs (after the response).
        assert len(tasks.tasks) == 1
        factory.session.add.assert_not_called()

        await tasks.run()
        [row] = _rows(factory)
        factory.session.commit.assert_awaited_once()
        assert row.entity_name == "TENANT" and row.entity_id == "7"
        assert row.action == "STATUS_CHANGE"
        assert row.previous_state == {"name": "Acme", "status": "ACTIVE"}
        assert row.new_state == {"name": "Acme", "status": "SUSPENDED"}
        assert row.performed_by == ACTOR
        assert row.trace_id == "trace-1"  # captured at log() time
        at = row.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        assert row.message == f"Widget 'Acme' ACTIVE -> SUSPENDED by {ACTOR} on {at}."

    async def test_without_background_tasks_writes_nothing(self, caplog) -> None:
        factory = _factory()
        with caplog.at_level(logging.WARNING):
            AuditLogWriter(factory).log(_trace(), AuditAction.STATUS_CHANGE, None, {"status": "X"})
        factory.session.add.assert_not_called()
        assert "not configured" in caplog.text

    async def test_unchanged_values_write_nothing(self) -> None:
        tasks = _Tasks()
        AuditLogWriter(_factory(), background_tasks=tasks).log(
            _trace(), AuditAction.STATUS_CHANGE, "x", {"status": "ACTIVE"}
        )
        assert tasks.tasks == []

    async def test_disabled_trace_writes_nothing(self) -> None:
        tasks = _Tasks()
        AuditLogWriter(_factory(), background_tasks=tasks).log(
            _trace(enabled=False), AuditAction.STATUS_CHANGE, "x", {"status": "X"}
        )
        assert tasks.tasks == []

    async def test_untracked_property_is_logged_not_raised(self, caplog) -> None:
        tasks = _Tasks()
        with caplog.at_level(logging.ERROR):
            AuditLogWriter(_factory(), background_tasks=tasks).log(
                _trace(), AuditAction.STATUS_CHANGE, "x", {"secret": "s"}
            )
        assert tasks.tasks == []
        assert "not tracked" in caplog.text

    async def test_no_session_factory_logs_warning(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            noop_audit_writer().log(_trace(), AuditAction.STATUS_CHANGE, "x", {"status": "X"})
        assert "not configured" in caplog.text

    async def test_insert_failure_is_logged_not_raised(self, caplog) -> None:
        factory, tasks = _factory(), _Tasks()
        factory.session.commit = AsyncMock(side_effect=RuntimeError("core db down"))
        AuditLogWriter(factory, background_tasks=tasks).log(
            _trace(), AuditAction.STATUS_CHANGE, "x", {"status": "X"}
        )
        with caplog.at_level(logging.ERROR):
            await tasks.run()
        assert "Audit row insert failed" in caplog.text


class TestBuildMessage:
    def test_missing_and_none_values_show_as_none(self) -> None:
        assert build_message("{a} {b} {c}", {"a": 1, "b": None}) == "1 none none."

    def test_broken_template_is_kept_as_is(self) -> None:
        assert build_message("bad {", {}) == "bad {."

    def test_actor_time_and_reason_are_added_in_order(self) -> None:
        values = {"performed_by": ACTOR, "at": "2026-11-11 07:11:21 UTC", "reason": "R"}
        assert build_message("Tenant 'A' suspended.", values) == (
            f"Tenant 'A' suspended by {ACTOR} on 2026-11-11 07:11:21 UTC. Reason: R."
        )

    def test_no_actor_leaves_out_by(self) -> None:
        assert build_message("Done", {"performed_by": None, "at": "T"}) == "Done on T."

    def test_reason_is_appended(self) -> None:
        assert build_message("Done.", {"reason": "Audit pending"}) == "Done. Reason: Audit pending."

    def test_blank_or_missing_reason_is_not_appended(self) -> None:
        assert build_message("Done.", {"reason": "  "}) == "Done."
        assert build_message("Done.", {"reason": None}) == "Done."
        assert build_message("Done.", {}) == "Done."

    def test_no_template_gives_no_message(self) -> None:
        assert build_message(None, {"a": 1}) is None


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
