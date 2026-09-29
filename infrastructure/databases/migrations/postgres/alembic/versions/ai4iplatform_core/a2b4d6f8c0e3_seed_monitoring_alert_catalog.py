"""seed_monitoring_alert_catalog

Seeds the 5 MONITORING-type rows from the "Define Monitoring Alerts" ticket
into configs_notification_alert, each with the ticket's default threshold
bands:

    ERROR_RATE_4XX  >=1% / >=5% / >=10%
    ERROR_RATE_5XX  >=1% / >=5% / >=10%
    LATENCY_P50     >=1s / >=2s / >=5s
    LATENCY_P95     >=2s / >=5s / >=10s
    LATENCY_P99     >=5s / >=10s / >=20s

Bands ship unchecked (active: false), same as the metering ALERT rows
(6dc231d5809a) — they exist so an Adopter Admin can turn them on, not
because any fire by default.

Stored under config.monitoring_thresholds, NOT config.thresholds: the
bands carry a value + unit (PERCENT or SECONDS) rather than a bare
percentage, and every reader of config.thresholds pinned today —
ai4i_core 1.0.34's notification_settings_cache (``band["percentage"]``)
and kafka-consumers' catalog_cache — assumes the metering band shape. An
active monitoring band under that key would raise inside refresh_all and
wedge the whole settings cache, not just these 5 rows.

Scope is GLOBAL (platform infrastructure, not per-institution) with the
Adopter Admin selected by default and Moderator available but off —
matching what e2a4c6b8d0f2 backfilled for every other GLOBAL row.

Revision ID: a2b4d6f8c0e3
Revises: f1a3c5e7b9d1
Create Date: 2026-09-28 00:00:00.000001

"""
import json
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2b4d6f8c0e3'
down_revision: Union[str, None] = 'f1a3c5e7b9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _bands(unit: str, *values) -> dict:
    return {
        "monitoring_thresholds": [
            {"value": value, "unit": unit, "active": False} for value in values
        ]
    }


_RECIPIENT_ROLES = {"ADMIN": True, "MODERATOR": False}

# (name, config)
_ROWS = [
    ("ERROR_RATE_4XX", _bands("PERCENT", 1, 5, 10)),
    ("ERROR_RATE_5XX", _bands("PERCENT", 1, 5, 10)),
    ("LATENCY_P50", _bands("SECONDS", 1, 2, 5)),
    ("LATENCY_P95", _bands("SECONDS", 2, 5, 10)),
    ("LATENCY_P99", _bands("SECONDS", 5, 10, 20)),
]


def _jsonb(value: dict) -> str:
    return "'{}'::jsonb".format(json.dumps(value).replace("'", "''"))


def upgrade() -> None:
    rows = ",\n    ".join(
        f"('{name}', 'MONITORING', 'MONITORING', '{{EMAIL}}', 'GLOBAL', "
        f"{_jsonb(_RECIPIENT_ROLES)}, {_jsonb(config)})"
        for name, config in _ROWS
    )
    op.execute(
        "INSERT INTO configs_notification_alert "
        "(name, type, module, channels, scope, recipient_roles, config) VALUES\n"
        f"    {rows}\n"
        "ON CONFLICT (name) DO NOTHING;"
    )


def downgrade() -> None:
    names = ",".join(f"'{name}'" for name, _ in _ROWS)
    # Subscription rows reference these by FK — clear them first. Targeted
    # delete, never TRUNCATE, same as every other catalog seed downgrade.
    op.execute(
        "DELETE FROM tenant_notification_subscription WHERE notification_id IN "
        f"(SELECT id FROM configs_notification_alert WHERE name IN ({names}));"
    )
    op.execute(f"DELETE FROM configs_notification_alert WHERE name IN ({names});")
