"""threshold_config_as_band_list

d5601baf6611 stored config.thresholds as a dict keyed by percent-as-string,
e.g. {"70": false, "80": false, "90": false} — the percentage itself was
the key, so an Adopter Admin editing a band's percentage had to delete one
key and add another, and the API had no natural way to express "these are
the same 3 bands, just with different numbers".

This migration reshapes config.thresholds from that dict into a list of
{"percentage": int, "active": bool} objects, order not meaningful — a band
is identified by nothing but its own percentage/active pair, and PATCH
replaces the whole list wholesale (see catalog_service.update_catalog).

Reads whatever is currently stored per row rather than hard-coding
70/80/90, so any environment where an Adopter Admin already toggled a band
on/off keeps that state across the migration instead of resetting to
disabled.

Revision ID: a3f5c7e9b1d3
Revises: d5601baf6611
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f5c7e9b1d3'
down_revision: Union[str, None] = 'd5601baf6611'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAMES = ["QUOTA_THRESHOLD", "BUDGET_THRESHOLD"]


def upgrade() -> None:
    names = ",".join(f"'{name}'" for name in _NAMES)
    op.execute(
        "UPDATE configs_notification_alert "
        "SET config = jsonb_set("
        "  config, '{thresholds}', "
        "  COALESCE("
        "    (SELECT jsonb_agg("
        "       jsonb_build_object('percentage', (key)::int, 'active', value::boolean) "
        "       ORDER BY (key)::int"
        "     ) FROM jsonb_each_text(config->'thresholds')),"
        "    '[]'::jsonb"
        "  )"
        ") "
        f"WHERE name IN ({names});"
    )


def downgrade() -> None:
    names = ",".join(f"'{name}'" for name in _NAMES)
    op.execute(
        "UPDATE configs_notification_alert "
        "SET config = jsonb_set("
        "  config, '{thresholds}', "
        "  COALESCE("
        "    (SELECT jsonb_object_agg(elem->>'percentage', elem->'active') "
        "     FROM jsonb_array_elements(config->'thresholds') AS elem),"
        "    '{}'::jsonb"
        "  )"
        ") "
        f"WHERE name IN ({names});"
    )
