"""Value objects shared by the cache, ledger, recipients and publisher, with
their fixed JSON forms (Redis values K1, K2, K3 and envelope fragments).
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Tuple

from . import constants as c
from .constants import (
    NotificationModule,
    NotificationName,
    NotificationScope,
    NotificationType,
    RecipientRole,
    Severity,
    ThresholdUnit,
)
from .keys import iso_z, json_number, ledger_key, parse_iso, subject_json, to_decimal


@dataclass(frozen=True)
class Band:
    value: Decimal
    unit: ThresholdUnit
    severity: Severity

    def to_json(self) -> Dict[str, Any]:
        return {"value": json_number(self.value), "unit": self.unit.value, "severity": self.severity.value}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Band":
        return cls(to_decimal(data["value"]), ThresholdUnit(data["unit"]), Severity(data["severity"]))

    def value_unit(self) -> Dict[str, Any]:
        """{value, unit} — the envelope's and error_detail's band shape."""
        return {"value": json_number(self.value), "unit": self.unit.value}


@dataclass(frozen=True)
class Measurement:
    """An observed value and its unit (BAND rule input)."""

    value: Decimal
    unit: ThresholdUnit

    def to_json(self) -> Dict[str, Any]:
        return {"value": json_number(self.value), "unit": self.unit.value}


@dataclass(frozen=True)
class SettingsRow:
    id: int
    name: NotificationName
    type: NotificationType
    module: NotificationModule
    scope: NotificationScope
    channels: Tuple[str, ...]
    recipient_roles: Dict[str, bool]
    #: Active bands only, ascending by value.
    bands: Tuple[Band, ...]

    def role_enabled(self, role: RecipientRole) -> bool:
        return bool(self.recipient_roles.get(role.value))

    def any_role_enabled(self) -> bool:
        return any(bool(on) for on in self.recipient_roles.values())

    def enabled_roles(self) -> Tuple[str, ...]:
        return tuple(sorted(role for role, on in self.recipient_roles.items() if on))

    def to_json(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "module": self.module.value,
            "scope": self.scope.value,
            "channels": list(self.channels),
            "recipient_roles": dict(self.recipient_roles),
            "bands": [band.to_json() for band in self.bands],
        }
        return data

    @classmethod
    def from_json(cls, name: str, data: Mapping[str, Any]) -> "SettingsRow":
        return cls(
            id=int(data["id"]),
            name=NotificationName(name),
            type=NotificationType(data["type"]),
            module=NotificationModule(data["module"]),
            scope=NotificationScope(data["scope"]),
            channels=tuple(data.get("channels") or ()),
            recipient_roles={str(k): bool(v) for k, v in (data.get("recipient_roles") or {}).items()},
            bands=tuple(sorted((Band.from_json(b) for b in data.get("bands") or ()), key=lambda b: b.value)),
        )


@dataclass(frozen=True)
class SettingsSnapshot:
    """K1 ntf:v1:settings — every catalog row with its active bands."""

    built_at: str
    rows: Dict[str, SettingsRow]

    def get(self, name) -> Optional[SettingsRow]:
        key = name.value if isinstance(name, NotificationName) else str(name)
        return self.rows.get(key)

    def to_json(self) -> Dict[str, Any]:
        return {
            "schema_version": c.SETTINGS_SNAPSHOT_SCHEMA_VERSION,
            "built_at": self.built_at,
            "rows": {name: row.to_json() for name, row in self.rows.items()},
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "SettingsSnapshot":
        if data.get("schema_version") != c.SETTINGS_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"unsupported settings snapshot schema_version {data.get('schema_version')!r}")
        return cls(
            built_at=str(data["built_at"]),
            rows={name: SettingsRow.from_json(name, row) for name, row in (data.get("rows") or {}).items()},
        )


@dataclass(frozen=True)
class SubscriptionEntry:
    subscribed: bool = False
    #: This tenant's own extra recipient user ids.
    recipients: Tuple[str, ...] = ()


_NO_SUBSCRIPTION = SubscriptionEntry()


@dataclass(frozen=True)
class TenantSubscriptions:
    """K2 ntf:v1:sub:{tenant_id} — every subscription row of one tenant."""

    tenant_id: str
    built_at: str
    rows: Dict[str, SubscriptionEntry] = field(default_factory=dict)

    def entry(self, name) -> SubscriptionEntry:
        key = name.value if isinstance(name, NotificationName) else str(name)
        return self.rows.get(key, _NO_SUBSCRIPTION)

    def to_json(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "built_at": self.built_at,
            "rows": {
                name: {"subscribed": entry.subscribed, "recipients": list(entry.recipients)}
                for name, entry in self.rows.items()
            },
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "TenantSubscriptions":
        return cls(
            tenant_id=str(data["tenant_id"]),
            built_at=str(data["built_at"]),
            rows={
                name: SubscriptionEntry(bool(entry.get("subscribed")), tuple(str(r) for r in entry.get("recipients") or ()))
                for name, entry in (data.get("rows") or {}).items()
            },
        )


@dataclass(frozen=True)
class LedgerState:
    """K3 ntf:v1:ledger:… — the ledger state of one BAND row (or no row yet)."""

    exists: bool
    current_band: Optional[Decimal]
    triggered: bool
    triggered_at: Optional[datetime]

    def to_json(self) -> Dict[str, Any]:
        return {
            "exists": self.exists,
            "current_band": json_number(self.current_band) if self.current_band is not None else None,
            "triggered": self.triggered,
            "triggered_at": iso_z(self.triggered_at) if self.triggered_at is not None else None,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "LedgerState":
        band = data.get("current_band")
        moment = data.get("triggered_at")
        return cls(
            exists=bool(data.get("exists")),
            current_band=to_decimal(band) if band is not None else None,
            triggered=bool(data.get("triggered")),
            triggered_at=parse_iso(moment) if moment else None,
        )


NO_LEDGER_ROW = LedgerState(exists=False, current_band=None, triggered=False, triggered_at=None)


@dataclass(frozen=True)
class LedgerRef:
    """Identity of one BAND ledger row plus its K3 key."""

    name: NotificationName
    tenant_id: str
    subject: Tuple[Tuple[str, str], ...]

    @classmethod
    def of(cls, name, tenant_id: str, subject: Mapping[str, str]) -> "LedgerRef":
        return cls(NotificationName(name), str(tenant_id), tuple(sorted(subject.items())))

    @property
    def subject_dict(self) -> Dict[str, str]:
        return dict(self.subject)

    @property
    def subject_json(self) -> str:
        return subject_json(self.subject_dict)

    @property
    def key(self) -> str:
        return ledger_key(self.name, self.tenant_id, self.subject_dict)


@dataclass(frozen=True)
class Recipient:
    email: str
    name: str

    def to_json(self) -> Dict[str, str]:
        return {"email": self.email, "name": self.name}
