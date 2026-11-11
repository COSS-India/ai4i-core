"""AuditLogWriter: record one ``audit_logs`` row per audited change.

Two calls around the real operation::

    trace = await audit.track(db, AuditEntity.TENANT, tenant_id, ["organisation", "status", "reason"])
    ...                                    # the endpoint's own DB work
    await db.commit()                      # the change is saved
    audit.log(                             # not awaited
        trace,
        AuditAction.STATUS_CHANGE,
        "Tenant '{organisation}' suspended by {performed_by} on {at}. Reason: {reason}.",
        {"status": "SUSPENDED", "reason": "Agreement renewal pending"},
        performed_by=current_user.id,
    )

``track`` reads the old values of ``properties`` from the database (the
entity's own session, before the change). ``log`` is called only after the
change is committed. It records the time and trace id right away and
schedules the insert to run after the response is sent, on its own
``ai4iplatform_core`` session, so the endpoint never waits for it.

Auditing never breaks the operation it records: ``track`` and ``log`` do not
raise for audit problems, and a failed insert is logged with the trace id.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Protocol, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai4i_core.audit.enums import AuditAction, AuditEntity
from ai4i_core.audit.models import AuditLog
from ai4i_core.audit.snapshot import get_audit_model, snapshot_query, to_json_value
from ai4i_core.context import get_trace_id

logger = logging.getLogger(__name__)

#: How ``{at}`` is shown in messages. Always UTC.
MESSAGE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
#: Shown in a message for a placeholder whose value is None or missing.
MESSAGE_EMPTY_VALUE = "none"
#: Added after the template: who made the change (when known) and when.
MESSAGE_ACTOR_SUFFIX = " by {performed_by}"
MESSAGE_TIME_SUFFIX = " on {at}"
#: Appended to every message whose new state has a non-empty ``reason``.
MESSAGE_REASON_SUFFIX = " Reason: {reason}."


class BackgroundTaskRunner(Protocol):
    """Anything with ``add_task(func, *args)``, e.g. FastAPI ``BackgroundTasks``."""

    def add_task(self, func: Any, *args: Any, **kwargs: Any) -> None: ...


@dataclass(frozen=True)
class AuditTrace:
    """Returned by ``track``: the entity and its values before the change.

    ``before`` is None when the row was not found. ``enabled`` is False when
    the old values could not be read; ``log`` then records nothing.
    """

    entity_name: AuditEntity
    entity_id: str
    properties: tuple[str, ...]
    before: Optional[dict[str, Any]]
    enabled: bool = True


@dataclass(frozen=True)
class _AuditRecord:
    entity_name: str
    entity_id: str
    action: str
    previous_state: Optional[dict[str, Any]]
    new_state: dict[str, Any]
    message_template: Optional[str]
    performed_by: Optional[UUID]
    created_at: datetime
    trace_id: Optional[str]


class _MessageValues(dict):
    def __missing__(self, key: str) -> str:
        return MESSAGE_EMPTY_VALUE


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def build_message(template: Optional[str], values: Mapping[str, Any]) -> Optional[str]:
    """Build the readable message for one row.

    ``template`` says what happened (``str.format`` placeholders, no trailing
    period needed). The library then adds, in order: `` by <performed_by>``
    (when set), `` on <at>`` (when set), a period, and `` Reason: <reason>.``
    when ``values`` has a non-empty ``reason``. Missing or None placeholder
    values show as ``MESSAGE_EMPTY_VALUE``; a broken template is used as is.
    """
    if template is None:
        return None
    message = _fill(template, values).rstrip().rstrip(".")
    if not _is_blank(values.get("performed_by")):
        message += MESSAGE_ACTOR_SUFFIX.format(performed_by=values["performed_by"])
    if not _is_blank(values.get("at")):
        message += MESSAGE_TIME_SUFFIX.format(at=values["at"])
    message += "."
    if not _is_blank(values.get("reason")):
        message += MESSAGE_REASON_SUFFIX.format(reason=values["reason"])
    return message


def _fill(template: str, values: Mapping[str, Any]) -> str:
    filled = _MessageValues(
        {k: (MESSAGE_EMPTY_VALUE if v is None or v == "" else v) for k, v in values.items()}
    )
    try:
        return template.format_map(filled)
    except (ValueError, IndexError, AttributeError) as exc:
        logger.error("Audit message template could not be filled: %r error=%s", template, exc)
        return template


class AuditLogWriter:
    """``session_factory`` makes ``ai4iplatform_core`` sessions and
    ``background_tasks`` (FastAPI's ``BackgroundTasks``) runs each insert
    after the response. Without either, nothing is recorded and a warning
    is logged.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]],
        background_tasks: Optional[BackgroundTaskRunner] = None,
    ) -> None:
        self._session_factory = session_factory
        self._background_tasks = background_tasks

    async def track(
        self,
        db: AsyncSession,
        entity_name: AuditEntity,
        entity_id: Any,
        properties: Sequence[str],
    ) -> AuditTrace:
        """Read the current values of ``properties`` for one entity row.

        ``db`` is the session the entity lives in (and will be changed in).
        Call it before the change.
        """
        if not isinstance(entity_name, AuditEntity):
            raise TypeError(f"entity_name must be an AuditEntity, got {entity_name!r}")
        props = tuple(properties)
        try:
            stmt = snapshot_query(get_audit_model(entity_name), entity_id, props)
        except (LookupError, ValueError) as exc:
            logger.error(
                "Audit track disabled for %s %s: %s trace_id=%s",
                entity_name.value, entity_id, exc, get_trace_id(),
            )
            return AuditTrace(entity_name, str(entity_id), props, None, enabled=False)
        try:
            row = (await db.execute(stmt)).mappings().first()
        except Exception as exc:
            logger.error(
                "Audit track could not read %s %s: %s trace_id=%s",
                entity_name.value, entity_id, exc, get_trace_id(), exc_info=True,
            )
            return AuditTrace(entity_name, str(entity_id), props, None, enabled=False)
        before = None if row is None else {k: to_json_value(row[k]) for k in props}
        return AuditTrace(entity_name, str(entity_id), props, before)

    def log(
        self,
        trace: AuditTrace,
        action: AuditAction,
        message_template: Optional[str],
        new_values: Mapping[str, Any],
        performed_by: Optional[UUID] = None,
    ) -> None:
        """Record the change. Call only after it is committed. Not awaited.

        ``new_values`` holds the tracked properties that changed; any tracked
        property not in it keeps its old value. ``message_template`` says what
        happened and may use every tracked property (new value),
        and ``previous_<property>`` (old value); the library
        adds who, when and the reason (see ``build_message``). Nothing is
        recorded when no value changed.
        """
        try:
            record = self._build_record(trace, action, message_template, new_values, performed_by)
            if record is None:
                return
            if self._session_factory is None or self._background_tasks is None:
                logger.warning(
                    "Audit row not written (platform-core DB or background tasks "
                    "not configured): %s %s %s trace_id=%s",
                    record.entity_name, record.entity_id, record.action, record.trace_id,
                )
                return
            self._background_tasks.add_task(self._write, record)
        except Exception as exc:
            logger.error(
                "Audit log failed for %s %s: %s trace_id=%s",
                getattr(trace, "entity_name", None), getattr(trace, "entity_id", None),
                exc, get_trace_id(), exc_info=True,
            )

    def _build_record(
        self,
        trace: AuditTrace,
        action: AuditAction,
        message_template: Optional[str],
        new_values: Mapping[str, Any],
        performed_by: Optional[UUID],
    ) -> Optional[_AuditRecord]:
        if not trace.enabled:
            return None
        if not isinstance(action, AuditAction):
            raise TypeError(f"action must be an AuditAction, got {action!r}")
        unknown = set(new_values) - set(trace.properties)
        if unknown:
            raise ValueError(f"new_values has properties not tracked: {sorted(unknown)}")
        before = trace.before
        after = dict(before or {})
        after.update({k: to_json_value(v) for k, v in new_values.items()})
        if before == after:
            return None
        return _AuditRecord(
            entity_name=trace.entity_name.value,
            entity_id=trace.entity_id,
            action=action.value,
            previous_state=before,
            new_state=after,
            message_template=message_template,
            performed_by=performed_by,
            created_at=datetime.now(timezone.utc),
            trace_id=get_trace_id(),
        )

    async def _write(self, record: _AuditRecord) -> None:
        """Insert one row on its own session. Never raises: an exception here
        would stop later background tasks of the same request (e.g. emails)."""
        values: dict[str, Any] = {
            f"previous_{k}": v for k, v in (record.previous_state or {}).items()
        }
        values.update(record.new_state)
        values.update(
            performed_by=record.performed_by,
            at=record.created_at.strftime(MESSAGE_TIME_FORMAT),
        )
        row = AuditLog(
            created_at=record.created_at,
            entity_name=record.entity_name,
            entity_id=record.entity_id,
            action=record.action,
            previous_state=record.previous_state,
            new_state=record.new_state,
            message=build_message(record.message_template, values),
            performed_by=record.performed_by,
            trace_id=record.trace_id,
        )
        try:
            async with self._session_factory() as session:
                session.add(row)
                await session.commit()
        except Exception as exc:
            logger.error(
                "Audit row insert failed: %s %s %s trace_id=%s error=%s",
                record.entity_name, record.entity_id, record.action, record.trace_id, exc,
                exc_info=True,
            )


def noop_audit_writer() -> AuditLogWriter:
    """Writer that records nothing. Default for services built outside
    request DI (scripts, tests)."""
    return AuditLogWriter(None)
