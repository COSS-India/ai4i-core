"""Subject validation and canonical forms, state fingerprints, Redis keys and
the Kafka message key.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Mapping

from . import constants as c
from .constants import SubjectKey
from .specs import NotificationSpec

_BILLING_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_AMOUNT_RE = re.compile(r"^\d+\.\d{%d}$" % c.AMOUNT_DECIMALS)
_AMOUNT_QUANTUM = Decimal(1).scaleb(-c.AMOUNT_DECIMALS)


class InvalidSubject(ValueError):
    """The subject does not match the fixed schema of its notification type."""


def _check_value(key: SubjectKey, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidSubject(f"{key.value} must be a non-empty string")
    if key is SubjectKey.BILLING_MONTH and not _BILLING_MONTH_RE.match(value):
        raise InvalidSubject(f"billing_month must be YYYY-MM, got {value!r}")
    if key is SubjectKey.MODEL_TASK_TYPE and value != value.lower():
        raise InvalidSubject(f"model_task_type must be lower case, got {value!r}")
    if key is SubjectKey.BUDGET_CEILING and not _AMOUNT_RE.match(value):
        raise InvalidSubject(f"budget_ceiling must have {c.AMOUNT_DECIMALS} decimals, got {value!r}")
    return value


def validate_subject(spec: NotificationSpec, subject: Mapping[str, Any]) -> Dict[str, str]:
    """A flat object with exactly the type's keys, all non-empty strings.
    Returns a plain dict copy; raises InvalidSubject otherwise."""
    if not isinstance(subject, Mapping):
        raise InvalidSubject("subject must be an object")
    expected = {key.value for key in spec.subject_keys}
    if set(subject) != expected:
        raise InvalidSubject(f"subject keys must be {sorted(expected)}, got {sorted(subject)}")
    return {key.value: _check_value(key, subject[key.value]) for key in spec.subject_keys}


def canonical_json(value: Any) -> str:
    """Sorted keys, no spaces — the one serialisation used for hashing and
    for JSONB parameters."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def subject_json(subject: Mapping[str, str]) -> str:
    return canonical_json(dict(subject))


def subject_key(subject: Mapping[str, str]) -> str:
    """key=value pairs, sorted by key, joined with ','; '_' when empty."""
    if not subject:
        return c.EMPTY_SUBJECT_KEY
    return ",".join(f"{key}={subject[key]}" for key in sorted(subject))


def state_hash(new_state: Mapping[str, Any]) -> str:
    """SHA-256 hex of the canonical JSON of a STATE event's new state."""
    return hashlib.sha256(canonical_json(dict(new_state)).encode("utf-8")).hexdigest()


def format_amount(value) -> str:
    """Amount as a string with 2 decimals, e.g. Decimal('5000') -> '5000.00'."""
    return str(Decimal(str(value)).quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP))


def billing_month_of(moment: datetime) -> str:
    return moment.strftime(c.BILLING_MONTH_FORMAT)


def quota_subject(billing_month: str, model_task_type: str) -> Dict[str, str]:
    return {
        SubjectKey.BILLING_MONTH.value: billing_month,
        SubjectKey.MODEL_TASK_TYPE.value: model_task_type.lower(),
    }


def budget_subject(allocated_budget) -> Dict[str, str]:
    """Budget alerts' period key: the tenant's allocated_budget."""
    return {SubjectKey.BUDGET_CEILING.value: format_amount(allocated_budget)}


def monitoring_subject(service_id: str) -> Dict[str, str]:
    return {SubjectKey.SERVICE_ID.value: service_id}


def quota_limit_subject(model_task_type: str) -> Dict[str, str]:
    return {SubjectKey.MODEL_TASK_TYPE.value: model_task_type.lower()}


# ── Redis and Kafka keys ────────────────────────────────────────────────────


def subscription_key(tenant_id: str) -> str:
    return f"{c.SUBSCRIPTION_KEY_PREFIX}{tenant_id}"


def ledger_key(name, tenant_id: str, subject: Mapping[str, str]) -> str:
    return f"{c.LEDGER_KEY_PREFIX}{_name(name)}:{tenant_id}:{subject_key(subject)}"


def kafka_message_key(name, tenant_id: str, subject: Mapping[str, str]) -> str:
    return f"{_name(name)}:{tenant_id}:{subject_key(subject)}"


def _name(name) -> str:
    return name.value if isinstance(name, c.NotificationName) else str(name)


# ── Numbers and times ───────────────────────────────────────────────────────


def to_decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def json_number(value):
    """Decimal -> int when whole, else float, for JSON output."""
    number = to_decimal(value)
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def display_number(value) -> str:
    """Decimal without trailing zeros and without an exponent: 80.0000 -> '80'."""
    text = format(to_decimal(value).normalize(), "f")
    return text


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(moment: datetime) -> str:
    """UTC, milliseconds, 'Z' suffix: 2026-09-28T10:15:00.000Z."""
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
