"""make daily_usage.fallback_count a JSON of fallback count, success and failure

Revision ID: b7d3f1a9c2e5
Revises: f1b2c3d4e5f6
Create Date: 2026-11-09

fallback_count becomes {"count": N, "success": S, "failure": F}: the request
rows sent to a fallback (sent_to_fallback), split by status (failure when it
is 400 or above; success = count - failure). Existing rows keep their count;
days already rolled up get their failures from usage_events' request rows,
grouped by the rollup's dimensions (fallbacks are only recorded since
ea3961c258e4, so only rows with a count need it).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7d3f1a9c2e5"
down_revision: Union[str, None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMPTY = """'{"count": 0, "success": 0, "failure": 0}'::jsonb"""
DIMENSIONS = (
    "tenant_id", "application_id", "api_key_id", "tier_id", "service_id", "inference_type_id", "billing_month",
)


def upgrade() -> None:
    op.execute("ALTER TABLE daily_usage ALTER COLUMN fallback_count DROP DEFAULT")
    op.execute(
        "ALTER TABLE daily_usage ALTER COLUMN fallback_count TYPE jsonb"
        " USING jsonb_build_object('count', fallback_count, 'success', fallback_count, 'failure', 0)"
    )
    op.execute(f"ALTER TABLE daily_usage ALTER COLUMN fallback_count SET DEFAULT {EMPTY}")

    match = " AND ".join(f"d.{c} IS NOT DISTINCT FROM f.{c}" for c in DIMENSIONS)
    op.execute(
        f"""
        UPDATE daily_usage d SET fallback_count = jsonb_build_object(
            'count', (d.fallback_count->>'count')::bigint,
            'success', (d.fallback_count->>'count')::bigint - f.failure,
            'failure', f.failure)
        FROM (
            SELECT (occurred_at AT TIME ZONE 'Asia/Kolkata')::date AS usage_date,
                   tenant_id, application_id, api_key_id, tier_id, service_id, inference_type_id,
                   to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM') AS billing_month,
                   count(*) AS failure
            FROM usage_events
            WHERE sent_to_fallback AND status_code >= 400 AND total_units = 0
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
        ) f
        WHERE (d.fallback_count->>'count')::bigint > 0 AND d.usage_date = f.usage_date AND {match}
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE daily_usage ALTER COLUMN fallback_count DROP DEFAULT")
    op.execute(
        "ALTER TABLE daily_usage ALTER COLUMN fallback_count TYPE bigint"
        " USING (fallback_count->>'count')::bigint"
    )
    op.execute("ALTER TABLE daily_usage ALTER COLUMN fallback_count SET DEFAULT 0")
