"""flatten every remaining domain-keyed policy_fields

f4a7c2e9d1b3 flattened only the seeded 'PII' row. Policy types saved while
platform-core required the domain-keyed shape
({"Finance": {"custom_field": [...]}, ...}) are still in it, and
inference-service's guardrail now refuses that shape (the request is blocked
rather than sent unmasked). This merges each row's domain sections into the
flat {"custom_field": [...], "model_supported_field": [...]} shape and trims
entity names the way platform-core's clean_name does.

A row that cannot be converted (an unknown shape, or an entry without a
usable entity_name or regex) is left as it is and named in the migration log;
fix it through the policy-type API.

Revision ID: a9d4f2b6c8e1
Revises: e2b4d6f8a0c3
Create Date: 2026-10-15

"""
import json
import logging
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9d4f2b6c8e1"
down_revision: Union[str, None] = "e2b4d6f8a0c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

FIELD_KEYS = ("custom_field", "model_supported_field")


def _clean(name: Any) -> Any:
    """platform-core's clean_name: trim whitespace and control/format
    characters (e.g. U+200B) from both ends. Non-strings are returned as is."""
    if not isinstance(name, str):
        return name
    invisible = lambda c: c.isspace() or unicodedata.category(c) in ("Cc", "Cf")  # noqa: E731
    start, end = 0, len(name)
    while start < end and invisible(name[start]):
        start += 1
    while end > start and invisible(name[end - 1]):
        end -= 1
    return name[start:end]


def _usable(v: Any) -> bool:
    return isinstance(v, str) and bool(v)


def _sections(policy_fields: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """The flat-shaped sections to merge, or None if the shape is unreadable.

    Flat keys sit at the top level; every other key must be a domain whose
    value is itself a flat section.
    """
    sections = [{k: policy_fields[k] for k in FIELD_KEYS if k in policy_fields}]
    for key, value in policy_fields.items():
        if key in FIELD_KEYS:
            continue
        if not isinstance(value, dict) or set(value) - set(FIELD_KEYS):
            return None
        sections.append(value)
    return sections


def flatten(policy_fields: Any) -> Optional[Dict[str, Any]]:
    """policy_fields in the flat shape, or None if it cannot be converted.

    Custom fields with the same entity_name and regex are kept once (the first
    one's examples win); model entities are merged per language, each name once.
    """
    if not isinstance(policy_fields, dict):
        return None
    sections = _sections(policy_fields)
    if sections is None:
        return None

    custom: List[Dict[str, Any]] = []
    seen_custom = set()
    model: Dict[str, List[Dict[str, Any]]] = {}
    seen_model: Dict[str, set] = {}
    for section in sections:
        entries = section.get("custom_field") or []
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            entry = {**entry, "entity_name": _clean(entry.get("entity_name"))}
            if not (_usable(entry["entity_name"]) and _usable(entry.get("regex"))
                    and entry["regex"].strip()):
                return None
            key = (entry["entity_name"], entry["regex"])
            if key not in seen_custom:
                seen_custom.add(key)
                custom.append(entry)

        by_language = section.get("model_supported_field") or []
        if not isinstance(by_language, list):
            return None
        for item in by_language:
            if not isinstance(item, dict):
                return None
            for lang, entities in item.items():
                if not isinstance(entities, list):
                    return None
                names = model.setdefault(lang, [])
                seen = seen_model.setdefault(lang, set())
                for entity in entities:
                    if not isinstance(entity, dict):
                        return None
                    entity = {**entity, "entity_name": _clean(entity.get("entity_name"))}
                    if not _usable(entity["entity_name"]):
                        return None
                    if entity["entity_name"] not in seen:
                        seen.add(entity["entity_name"])
                        names.append(entity)

    flat: Dict[str, Any] = {}
    if custom or "custom_field" in policy_fields:
        flat["custom_field"] = custom
    if model or "model_supported_field" in policy_fields:
        flat["model_supported_field"] = [model] if model else []
    return flat


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, policy_type, policy_fields FROM policy_type")).fetchall()
    for row_id, name, policy_fields in rows:
        if policy_fields is None:
            continue
        flat = flatten(policy_fields)
        if flat is None:
            logger.warning(
                "policy_type id=%s (%r): policy_fields is not in a shape this migration "
                "can flatten; left unchanged", row_id, name,
            )
            continue
        # Already flat, with nothing to merge or trim: no write.
        if flat == policy_fields:
            continue
        bind.execute(
            sa.text("UPDATE policy_type SET policy_fields = CAST(:fields AS JSONB) WHERE id = :id"),
            {"fields": json.dumps(flat), "id": row_id},
        )
        logger.info("policy_type id=%s (%r): policy_fields flattened", row_id, name)


def downgrade() -> None:
    # The domain each entry came from is not kept, so the old shape cannot be
    # rebuilt. The flat shape is what every current reader expects.
    pass
