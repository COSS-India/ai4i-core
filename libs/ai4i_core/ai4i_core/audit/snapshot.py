"""JSON snapshot of an audited ORM object.

A snapshot is the object's mapped column values, minus bookkeeping columns,
with every value converted to something JSON can hold. Two snapshots of an
unchanged object are equal, which is what lets the writer skip no-op changes.

Columns typed with a ``TypeDecorator`` (e.g. auth-service's encrypted email
and phone columns) are stored in their bound form — exactly what the column
holds in the database. For the deterministic PII encryption that means the
ciphertext, so the audit table never holds plaintext PII while a changed
value still produces a different snapshot (masking would not: two different
emails can mask to the same string).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Callable, Mapping, Optional
from uuid import UUID

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.types import TypeDecorator

from ai4i_core.audit.enums import AuditEntity

#: Columns that change on every write (or never) and say nothing about the
#: entity itself. Left out of every snapshot unless a rule says otherwise.
BOOKKEEPING_COLUMNS: frozenset[str] = frozenset(
    {"created_at", "updated_at", "created_by", "updated_by"}
)


@dataclass(frozen=True)
class SnapshotRule:
    """How one entity type is snapshotted.

    ``exclude``: column keys left out. ``extras``: extra keys computed from
    the object (sync callables, called with the object; must not trigger I/O).
    State that needs a query, such as a user's roles, is passed per call
    through ``AuditLogWriter.track(extra=...)`` instead.
    """

    exclude: frozenset[str] = BOOKKEEPING_COLUMNS
    extras: Mapping[str, Callable[[Any], Any]] = field(default_factory=dict)


_RULES: dict[AuditEntity, SnapshotRule] = {
    AuditEntity.TENANT: SnapshotRule(),
    # last_login changes on every sign-in; it is not an audited change.
    AuditEntity.TENANT_USER: SnapshotRule(exclude=BOOKKEEPING_COLUMNS | {"last_login"}),
}


def register_snapshot_rule(entity: AuditEntity, rule: SnapshotRule) -> None:
    """Set (or replace) the rule for ``entity``."""
    _RULES[entity] = rule


def get_snapshot_rule(entity: AuditEntity) -> SnapshotRule:
    return _RULES.get(entity, SnapshotRule())


def to_json_value(value: Any) -> Any:
    """Convert ``value`` (recursively) to a JSON-native value."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, enum.Enum):
        return to_json_value(value.value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        # str, not float: budgets are NUMERIC and must not pick up float noise.
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): to_json_value(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((to_json_value(v) for v in value), key=repr)
    if isinstance(value, (list, tuple)):
        return [to_json_value(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _column_values(obj: Any, exclude: frozenset[str]) -> dict[str, Any]:
    if isinstance(obj, Mapping):
        return {k: v for k, v in obj.items() if k not in exclude}
    state = sa_inspect(obj)
    loaded = state.dict
    out: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in exclude:
            continue
        # Read only what is already loaded: touching an expired or unloaded
        # attribute would lazy-load, which fails on an AsyncSession.
        if key not in loaded:
            continue
        value = loaded[key]
        column_type = attr.columns[0].type
        if value is not None and isinstance(column_type, TypeDecorator):
            value = column_type.process_bind_param(value, None)
        out[key] = value
    return out


def snapshot(
    entity_type: AuditEntity,
    obj: Any,
    extra: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Snapshot ``obj`` (an ORM instance, or a plain mapping) for ``entity_type``.

    ``extra`` is merged in last, e.g. ``{"roles": [...]}`` for a user.
    """
    rule = get_snapshot_rule(entity_type)
    values = _column_values(obj, rule.exclude)
    for key, compute in rule.extras.items():
        values[key] = compute(obj)
    if extra:
        values.update(extra)
    return {key: to_json_value(value) for key, value in values.items()}
