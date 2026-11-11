"""Which ORM model each audited entity is read from, and JSON conversion.

A service registers its models once at import time::

    register_audit_entity(AuditEntity.TENANT, Tenant)

``AuditLogWriter.track`` then reads the requested properties of one row of
that model straight from the database.

Columns typed with a ``TypeDecorator`` (e.g. auth-service's encrypted email
and phone columns) are read in their stored form, so the audit table never
holds plaintext PII. This is done with ``type_coerce`` to the decorator's
underlying type, which needs no dialect and works for any decorator.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Mapping, Sequence
from uuid import UUID

from sqlalchemy import Select, inspect as sa_inspect, select, type_coerce
from sqlalchemy.types import TypeDecorator

from ai4i_core.audit.enums import AuditEntity

_MODELS: dict[AuditEntity, type] = {}


def register_audit_entity(entity: AuditEntity, model: type) -> None:
    """Map ``entity`` to the ORM model its rows are read from. The model must
    have a single-column primary key."""
    if len(sa_inspect(model).primary_key) != 1:
        raise ValueError(f"{model.__name__} must have a single-column primary key")
    _MODELS[entity] = model


def get_audit_model(entity: AuditEntity) -> type:
    try:
        return _MODELS[entity]
    except KeyError:
        raise LookupError(
            f"No model registered for audit entity {entity.value}; "
            "call register_audit_entity() first"
        ) from None


def snapshot_query(model: type, entity_id: Any, properties: Sequence[str]) -> Select:
    """``SELECT <properties> FROM <model> WHERE <pk> = entity_id``.

    Raises ``ValueError`` for a property that is not a mapped column.
    """
    mapper = sa_inspect(model)
    columns = []
    for prop in properties:
        attr = mapper.column_attrs.get(prop)
        if attr is None:
            raise ValueError(f"{model.__name__} has no column {prop!r}")
        column = attr.columns[0]
        if isinstance(column.type, TypeDecorator):
            # Stored form (e.g. ciphertext), not the decoded Python value.
            columns.append(type_coerce(column, column.type.impl_instance).label(prop))
        else:
            columns.append(column.label(prop))
    pk = mapper.primary_key[0]
    return select(*columns).where(pk == entity_id)


def to_json_value(value: Any) -> Any:
    """Convert ``value`` (recursively) to a JSON-native value."""
    # Enum first: a str/int-based enum (e.g. TenantStatus) is also a str/int.
    if isinstance(value, enum.Enum):
        return to_json_value(value.value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
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
