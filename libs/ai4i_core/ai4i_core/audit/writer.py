"""AuditLogWriter — records one ``audit_logs`` row per audited change.

Usage (entity stored in another database, e.g. ai4iplatform_auth)::

    async with audit.track(AuditEntity.TENANT, tenant, AuditAction.STATUS_CHANGE,
                           performed_by=current_user.id) as t:
        tenant.status = new_status
        t.message = tenant_status_changed(t.before, t.after_now(), users_affected)
    await tenants.save_and_refresh(tenant)   # 1. commit the entity
    await audit.commit()                     # 2. commit the audit row

If the entity commit raises, ``audit.commit()`` is never reached and the row is
dropped with the session. If ``audit.commit()`` fails it logs an ERROR with the
trace id and returns: the entity change is already committed and stays.

For an entity stored in ``ai4iplatform_core`` itself, build the writer on the
entity's own session with ``isolated=False`` and skip ``audit.commit()``: the
service's commit covers both rows, and errors propagate as usual.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping, Optional
from uuid import UUID

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from ai4i_core.audit.enums import AuditAction, AuditEntity
from ai4i_core.audit.models import AuditLog
from ai4i_core.audit.snapshot import snapshot
from ai4i_core.context import get_trace_id

logger = logging.getLogger(__name__)

#: Async callable returning extra snapshot keys that need a query, e.g. a
#: user's roles. Called on enter (except for CREATE) and on exit.
ExtraLoader = Callable[[], Awaitable[Mapping[str, Any]]]


class AuditTracker:
    """Handle yielded by ``AuditLogWriter.track``.

    ``before`` is the snapshot taken on enter (None for CREATE). Set
    ``message`` inside the block to store a readable summary with the row.
    """

    def __init__(
        self,
        entity_name: AuditEntity,
        obj: Any,
        before: Optional[dict],
        extra: Optional[Mapping[str, Any]],
    ) -> None:
        self.entity_name = entity_name
        self.obj = obj
        self.before = before
        self.message: Optional[str] = None
        self._extra = extra

    def after_now(self) -> dict:
        """Snapshot of the object as it is right now, inside the block.

        Extra keys from an ``extra`` loader are the ones read on enter; the
        exit snapshot re-reads them.
        """
        return snapshot(self.entity_name, self.obj, extra=self._extra)


def _entity_id_of(obj: Any) -> Optional[str]:
    if isinstance(obj, Mapping):
        value = obj.get("id")
        return None if value is None else str(value)
    state = sa_inspect(obj)
    keys = [col.key for col in state.mapper.primary_key]
    values = [state.dict.get(k) for k in keys]
    if any(v is None for v in values):
        return None
    return ":".join(str(v) for v in values)


class AuditLogWriter:
    """Writes audit rows on an ``ai4iplatform_core`` session.

    ``session`` may be None (platform-core DB not configured): ``track`` then
    still runs the block but records nothing, and logs a warning.

    ``isolated=True`` (default) means the session holds nothing but audit
    rows, so a failure to write is logged and swallowed — auditing never
    breaks the operation it records. ``isolated=False`` is for a session
    shared with the audited entity, where a failure must propagate.
    """

    def __init__(self, session: Optional[AsyncSession], *, isolated: bool = True) -> None:
        self._session = session
        self._isolated = isolated

    @asynccontextmanager
    async def track(
        self,
        entity_name: AuditEntity,
        obj: Any,
        action: AuditAction,
        performed_by: Optional[UUID] = None,
        *,
        entity_id: Optional[str] = None,
        extra: Optional[ExtraLoader] = None,
    ) -> AsyncIterator[AuditTracker]:
        if not isinstance(entity_name, AuditEntity):
            raise TypeError(f"entity_name must be an AuditEntity, got {entity_name!r}")
        if not isinstance(action, AuditAction):
            raise TypeError(f"action must be an AuditAction, got {action!r}")

        if action is AuditAction.CREATE:
            before_extra, before = None, None
        else:
            before_extra = dict(await extra()) if extra else None
            before = snapshot(entity_name, obj, extra=before_extra)

        tracker = AuditTracker(entity_name, obj, before, before_extra)
        # An exception in the block propagates from here, so nothing is recorded.
        yield tracker

        after_extra = dict(await extra()) if extra else None
        after = snapshot(entity_name, obj, extra=after_extra)
        if before == after:
            return

        resolved_id = entity_id or _entity_id_of(obj)
        trace_id = get_trace_id()
        if self._session is None:
            logger.warning(
                "Audit row not written (platform-core DB not configured): %s %s %s trace_id=%s",
                entity_name.value, resolved_id, action.value, trace_id,
            )
            return
        if resolved_id is None:
            logger.error(
                "Audit row not written: %s has no primary key yet (flush before the "
                "block ends or pass entity_id) action=%s trace_id=%s",
                entity_name.value, action.value, trace_id,
            )
            return

        row = AuditLog(
            entity_name=entity_name.value,
            entity_id=resolved_id,
            action=action.value,
            previous_state=before,
            new_state=after,
            message=tracker.message,
            performed_by=performed_by,
            trace_id=trace_id,
        )
        try:
            self._session.add(row)
            await self._session.flush()
        except Exception as exc:
            if not self._isolated:
                raise
            logger.error(
                "Audit row flush failed: %s %s %s trace_id=%s error=%s",
                entity_name.value, resolved_id, action.value, trace_id, exc,
                exc_info=True,
            )
            await self._safe_rollback()

    async def commit(self) -> bool:
        """Commit the audit session. Returns False (after logging) on failure.

        Never raises: the audited entity is already committed in its own
        database, and a missing audit row must not turn that into an error.
        """
        if self._session is None:
            return False
        try:
            await self._session.commit()
            return True
        except Exception as exc:
            logger.error(
                "Audit log commit failed; entity change kept. trace_id=%s error=%s",
                get_trace_id(), exc,
                exc_info=True,
            )
            await self._safe_rollback()
            return False

    async def _safe_rollback(self) -> None:
        try:
            await self._session.rollback()
        except Exception:
            logger.exception("Audit session rollback failed trace_id=%s", get_trace_id())
