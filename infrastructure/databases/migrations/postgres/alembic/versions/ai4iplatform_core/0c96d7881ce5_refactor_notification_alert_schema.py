"""refactor_notification_alert_schema

Moves the notification tables to the producer-side design (models in
services/platform-core-service/app/models/notification_management):

* notification_alert_threshold — new. One typed row per threshold band,
  loaded once from the JSON band lists in configs_notification_alert.config
  ("thresholds" and "monitoring_thresholds"). Severity is counted from the
  top of each row's ladder: highest CRITICAL, second WARNING, rest INFO. The
  two EXHAUSTED rows get a fixed, non-editable 100 % CRITICAL band.
* configs_notification_alert — "config" and its GIN channels index are
  dropped (bands now live in notification_alert_threshold). Every
  recipient-role flag is reset to false, so no one is assigned until an
  admin picks recipients. New checks: recipient_roles is an object that
  carries every legal key for the row's type, and MONITORING rows are
  always GLOBAL.
* monitoring_alert_recipient — cleared to match the reset role flags, and
  role is checked to be ADMIN or MODERATOR.
* tenant_notification_subscription — FK now cascades on delete. Rows for
  MONITORING notifications are removed: monitoring alerts have no tenant.
* ledger_notification_alert — rebuilt without channel/status. One row per
  (notification, tenant, subject) holding either a band (current_band) or
  a fingerprint (state_hash), plus the triggered flag. Starts empty.
* notification_alert_failure_log — new. Write-once record of producer-side
  failures before the Kafka handoff.

Revision ID: 0c96d7881ce5
Revises: b3c5e7a9d1f4
Create Date: 2026-09-28 00:00:00.000001

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0c96d7881ce5'
down_revision: Union[str, None] = 'b3c5e7a9d1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Tables ───────────────────────────────────────────────────────────────────
CATALOG_TABLE = "configs_notification_alert"
THRESHOLD_TABLE = "notification_alert_threshold"
SUBSCRIPTION_TABLE = "tenant_notification_subscription"
MONITORING_RECIPIENT_TABLE = "monitoring_alert_recipient"
LEDGER_TABLE = "ledger_notification_alert"
FAILURE_LOG_TABLE = "notification_alert_failure_log"

CATALOG_FK = "configs_notification_alert.id"
SUBSCRIPTION_FK = "fk_tenant_notification_subscription_notification_id"
CHANNELS_GIN_INDEX = "ix_configs_notification_alert_channels"

# ── Enum types ───────────────────────────────────────────────────────────────
CHANNEL_ENUM = "notification_alert_channel_enum"
THRESHOLD_UNIT_ENUM = "notification_threshold_unit_enum"
SEVERITY_ENUM = "notification_severity_enum"
FAILURE_STAGE_ENUM = "notification_failure_stage_enum"

UNIT_PERCENT = "PERCENT"
UNIT_SECONDS = "SECONDS"
SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"

THRESHOLD_UNITS = [UNIT_PERCENT, UNIT_SECONDS]
SEVERITIES = [SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL]
FAILURE_STAGES = [
    "VALIDATION", "SETTINGS", "SUBSCRIPTION", "SOURCE", "LEDGER",
    "DETAILS", "RECIPIENTS", "PUBLISH", "CACHE",
]
CHANNELS = ["EMAIL", "SMS", "SLACK", "WHATSAPP"]

# ── Catalog values ───────────────────────────────────────────────────────────
TYPE_MONITORING = "MONITORING"
TYPE_ALERT = "ALERT"
SCOPE_GLOBAL = "GLOBAL"

ROLE_ADMIN = "ADMIN"
ROLE_TENANT_ADMIN = "TENANT ADMIN"
ROLE_MODERATOR = "MODERATOR"
MONITORING_ROLES = [ROLE_ADMIN, ROLE_MODERATOR]
TENANT_ROLES = [ROLE_ADMIN, ROLE_TENANT_ADMIN]

# Seeded with no one assigned: every role flag false.
NO_MONITORING_RECIPIENTS = {role: False for role in MONITORING_ROLES}
NO_TENANT_RECIPIENTS = {role: False for role in TENANT_ROLES}
# What b3c5e7a9d1f4 left on the monitoring rows (a2b4d6f8c0e3 seed).
PREVIOUS_MONITORING_RECIPIENTS = {ROLE_ADMIN: True, ROLE_MODERATOR: False}

EXHAUSTED_NAMES = ["QUOTA_EXHAUSTED", "BUDGET_EXHAUSTED"]
EXHAUSTED_BAND_VALUE = 100

# JSON keys of the legacy band lists in configs_notification_alert.config.
CONFIG_THRESHOLDS_KEY = "thresholds"
CONFIG_MONITORING_THRESHOLDS_KEY = "monitoring_thresholds"

PRODUCERS = ["auth-service", "platform-core-service", "payperuse-consumer", "monitoring-evaluator"]


def _jsonb(value) -> str:
    return "'{}'::jsonb".format(json.dumps(value).replace("'", "''"))


def _sql_list(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _enum(name: str, values) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _audit_columns():
    return [
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def _create_enum_types() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*THRESHOLD_UNITS, name=THRESHOLD_UNIT_ENUM).create(bind, checkfirst=True)
    postgresql.ENUM(*SEVERITIES, name=SEVERITY_ENUM).create(bind, checkfirst=True)
    postgresql.ENUM(*FAILURE_STAGES, name=FAILURE_STAGE_ENUM).create(bind, checkfirst=True)


def _reset_recipients() -> None:
    # No one assigned at first: every recipient-role flag false.
    op.execute(
        f"""
        UPDATE {CATALOG_TABLE}
           SET recipient_roles = CASE WHEN type = '{TYPE_MONITORING}'
                                      THEN {_jsonb(NO_MONITORING_RECIPIENTS)}
                                      ELSE {_jsonb(NO_TENANT_RECIPIENTS)}
                                 END
        """
    )
    op.execute(f"DELETE FROM {MONITORING_RECIPIENT_TABLE}")
    op.create_check_constraint(
        "ck_monitoring_alert_recipient_role",
        MONITORING_RECIPIENT_TABLE,
        f"role IN ({_sql_list(MONITORING_ROLES)})",
    )
    # Monitoring alerts have no tenant, so a per-tenant subscription row for
    # one means nothing.
    op.execute(
        f"DELETE FROM {SUBSCRIPTION_TABLE} WHERE notification_id IN "
        f"(SELECT id FROM {CATALOG_TABLE} WHERE type = '{TYPE_MONITORING}')"
    )


def _create_threshold_table() -> None:
    op.create_table(
        THRESHOLD_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("band_value", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit", _enum(THRESHOLD_UNIT_ENUM, THRESHOLD_UNITS), nullable=False),
        sa.Column("severity", _enum(SEVERITY_ENUM, SEVERITIES), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("editable", sa.Boolean(), nullable=False, server_default="true"),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["notification_id"], [CATALOG_FK],
            name="fk_notification_alert_threshold_notification_id", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("notification_id", "band_value", name="uq_notification_alert_threshold_band"),
        sa.CheckConstraint("band_value > 0", name="ck_notification_alert_threshold_positive"),
        sa.CheckConstraint(
            f"unit <> '{UNIT_PERCENT}' OR band_value <= 100", name="ck_notification_alert_threshold_percent"
        ),
    )
    op.create_index(
        "ix_notification_alert_threshold_active", THRESHOLD_TABLE, ["notification_id"],
        postgresql_where=sa.text("active"),
    )


def _load_bands() -> None:
    # Bands from the JSON band lists, as they are (a row with 2 bands keeps
    # 2). A value listed twice becomes one band, active if either copy was.
    op.execute(
        f"""
        INSERT INTO {THRESHOLD_TABLE} (notification_id, band_value, unit, severity, active, editable)
        SELECT b.notification_id, b.band_value, b.unit::{THRESHOLD_UNIT_ENUM},
               (CASE row_number() OVER (PARTITION BY b.notification_id ORDER BY b.band_value DESC)
                     WHEN 1 THEN '{SEVERITY_CRITICAL}'
                     WHEN 2 THEN '{SEVERITY_WARNING}'
                     ELSE '{SEVERITY_INFO}'
                END)::{SEVERITY_ENUM},
               b.active, true
          FROM (SELECT raw.notification_id, raw.band_value,
                       min(raw.unit) AS unit, bool_or(raw.active) AS active
                  FROM (SELECT c.id AS notification_id,
                               (e->>'percentage')::numeric AS band_value,
                               '{UNIT_PERCENT}' AS unit,
                               COALESCE((e->>'active')::boolean, false) AS active
                          FROM {CATALOG_TABLE} c,
                               jsonb_array_elements(
                                   CASE WHEN jsonb_typeof(c.config->'{CONFIG_THRESHOLDS_KEY}') = 'array'
                                        THEN c.config->'{CONFIG_THRESHOLDS_KEY}'
                                        ELSE '[]'::jsonb END) AS e
                        UNION ALL
                        SELECT c.id,
                               (e->>'value')::numeric,
                               e->>'unit',
                               COALESCE((e->>'active')::boolean, false)
                          FROM {CATALOG_TABLE} c,
                               jsonb_array_elements(
                                   CASE WHEN jsonb_typeof(c.config->'{CONFIG_MONITORING_THRESHOLDS_KEY}') = 'array'
                                        THEN c.config->'{CONFIG_MONITORING_THRESHOLDS_KEY}'
                                        ELSE '[]'::jsonb END) AS e
                       ) raw
                 WHERE raw.band_value IS NOT NULL
                 GROUP BY raw.notification_id, raw.band_value
               ) b
        """
    )
    # Fixed 100 % band of the two EXHAUSTED rows.
    op.execute(
        f"""
        INSERT INTO {THRESHOLD_TABLE} (notification_id, band_value, unit, severity, active, editable)
        SELECT id, {EXHAUSTED_BAND_VALUE}, '{UNIT_PERCENT}', '{SEVERITY_CRITICAL}', true, false
          FROM {CATALOG_TABLE}
         WHERE name IN ({_sql_list(EXHAUSTED_NAMES)})
        ON CONFLICT (notification_id, band_value) DO NOTHING
        """
    )


def _finish_catalog_table() -> None:
    op.drop_index(CHANNELS_GIN_INDEX, table_name=CATALOG_TABLE)
    op.drop_column(CATALOG_TABLE, "config")
    op.create_check_constraint(
        "ck_configs_notification_alert_roles", CATALOG_TABLE, "jsonb_typeof(recipient_roles) = 'object'"
    )
    op.create_check_constraint(
        "ck_configs_notification_alert_role_keys",
        CATALOG_TABLE,
        f"(type = '{TYPE_MONITORING}' AND recipient_roles ?& ARRAY[{_sql_list(MONITORING_ROLES)}])"
        f" OR (type <> '{TYPE_MONITORING}' AND recipient_roles ?& ARRAY[{_sql_list(TENANT_ROLES)}])",
    )
    op.create_check_constraint(
        "ck_configs_notification_alert_mon_scope",
        CATALOG_TABLE,
        f"type <> '{TYPE_MONITORING}' OR scope = '{SCOPE_GLOBAL}'",
    )


def _set_subscription_fk(ondelete) -> None:
    op.drop_constraint(SUBSCRIPTION_FK, SUBSCRIPTION_TABLE, type_="foreignkey")
    op.create_foreign_key(
        SUBSCRIPTION_FK, SUBSCRIPTION_TABLE, CATALOG_TABLE, ["notification_id"], ["id"], ondelete=ondelete
    )


def _create_ledger_table() -> None:
    # The ledger starts empty: a tenant already above a band gets that
    # band's alert once more, on its next evaluation.
    op.create_table(
        LEDGER_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("current_band", sa.Numeric(12, 4), nullable=True),
        sa.Column("state_hash", sa.CHAR(64), nullable=True),
        sa.Column("triggered", sa.Boolean(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["notification_id"], [CATALOG_FK], name="fk_ledger_notification_alert_notification_id"),
        sa.UniqueConstraint("notification_id", "tenant_id", "subject", name="uq_ledger_notification_alert_identity"),
        sa.CheckConstraint("jsonb_typeof(subject) = 'object'", name="ck_ledger_notification_alert_subject"),
        sa.CheckConstraint(
            "(current_band IS NULL) <> (state_hash IS NULL)", name="ck_ledger_notification_alert_one_value"
        ),
    )
    op.create_index(
        "ix_ledger_notification_alert_tenant_updated", LEDGER_TABLE, ["tenant_id", sa.text("updated_at DESC")]
    )
    op.create_index(
        "ix_ledger_notification_alert_open", LEDGER_TABLE, ["notification_id"], postgresql_where=sa.text("triggered")
    )


def _create_previous_ledger_table() -> None:
    """The ledger shape of 8f754a278bee, for the downgrade."""
    op.create_table(
        LEDGER_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("channel", _enum(CHANNEL_ENUM, CHANNELS), nullable=False),
        sa.Column("status", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["notification_id"], [CATALOG_FK], name="fk_ledger_notification_alert_notification_id"),
        sa.UniqueConstraint(
            "notification_id", "tenant_id", "subject", "channel", name="uq_ledger_notification_alert_identity"
        ),
    )
    op.create_index("ix_ledger_notification_alert_notification_id", LEDGER_TABLE, ["notification_id"])
    op.create_index("ix_ledger_notification_alert_tenant", LEDGER_TABLE, ["tenant_id", "updated_at"])


def _create_failure_log_table() -> None:
    op.create_table(
        FAILURE_LOG_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notification_name", sa.String(length=64), nullable=False),
        sa.Column("notification_id", sa.BigInteger(), nullable=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("subject", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("producer", sa.String(length=64), nullable=False),
        sa.Column("pod_name", sa.String(length=255), nullable=True),
        sa.Column("stage", _enum(FAILURE_STAGE_ENUM, FAILURE_STAGES), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("error_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["notification_id"], [CATALOG_FK],
            name="fk_notification_alert_failure_log_notification_id", ondelete="SET NULL",
        ),
        sa.CheckConstraint(f"producer IN ({_sql_list(PRODUCERS)})", name="ck_failure_log_producer"),
        sa.CheckConstraint("jsonb_typeof(error_detail) = 'object'", name="ck_failure_log_detail"),
    )
    op.create_index(
        "ix_failure_log_name_created", FAILURE_LOG_TABLE, ["notification_name", sa.text("created_at DESC")]
    )
    op.create_index(
        "ix_failure_log_event", FAILURE_LOG_TABLE, ["event_id"], postgresql_where=sa.text("event_id IS NOT NULL")
    )


def upgrade() -> None:
    _create_enum_types()
    _reset_recipients()
    _create_threshold_table()
    _load_bands()
    _finish_catalog_table()
    _set_subscription_fk(ondelete="CASCADE")
    op.drop_table(LEDGER_TABLE)
    _create_ledger_table()
    _create_failure_log_table()


def downgrade() -> None:
    op.drop_table(FAILURE_LOG_TABLE)
    op.drop_table(LEDGER_TABLE)
    _create_previous_ledger_table()
    _set_subscription_fk(ondelete=None)

    op.drop_constraint("ck_configs_notification_alert_mon_scope", CATALOG_TABLE, type_="check")
    op.drop_constraint("ck_configs_notification_alert_role_keys", CATALOG_TABLE, type_="check")
    op.drop_constraint("ck_configs_notification_alert_roles", CATALOG_TABLE, type_="check")

    # Bands back into the JSON band lists.
    op.add_column(
        CATALOG_TABLE,
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.execute(
        f"""
        UPDATE {CATALOG_TABLE} c
           SET config = jsonb_build_object(
                   '{CONFIG_THRESHOLDS_KEY}',
                   (SELECT COALESCE(jsonb_agg(jsonb_build_object(
                               'percentage', round(t.band_value)::int, 'active', t.active)
                           ORDER BY t.band_value), '[]'::jsonb)
                      FROM {THRESHOLD_TABLE} t
                     WHERE t.notification_id = c.id))
         WHERE c.type = '{TYPE_ALERT}'
        """
    )
    op.execute(
        f"""
        UPDATE {CATALOG_TABLE} c
           SET config = jsonb_build_object(
                   '{CONFIG_MONITORING_THRESHOLDS_KEY}',
                   (SELECT COALESCE(jsonb_agg(jsonb_build_object(
                               'value', trim_scale(t.band_value), 'unit', t.unit, 'active', t.active)
                           ORDER BY t.band_value), '[]'::jsonb)
                      FROM {THRESHOLD_TABLE} t
                     WHERE t.notification_id = c.id))
         WHERE c.type = '{TYPE_MONITORING}'
        """
    )
    op.create_index(CHANNELS_GIN_INDEX, CATALOG_TABLE, ["channels"], postgresql_using="gin")
    op.drop_index("ix_notification_alert_threshold_active", table_name=THRESHOLD_TABLE)
    op.drop_table(THRESHOLD_TABLE)

    # Previous recipient flags: ADMIN follows scope on metering rows
    # (e2a4c6b8d0f2); monitoring rows go back to their seed value. Cleared
    # monitoring recipients are not restored: the next monitoring catalog
    # save rebuilds them.
    op.execute(
        f"UPDATE {CATALOG_TABLE} "
        f"SET recipient_roles = jsonb_build_object('{ROLE_ADMIN}', scope = '{SCOPE_GLOBAL}') "
        f"WHERE type <> '{TYPE_MONITORING}'"
    )
    op.execute(
        f"UPDATE {CATALOG_TABLE} SET recipient_roles = {_jsonb(PREVIOUS_MONITORING_RECIPIENTS)} "
        f"WHERE type = '{TYPE_MONITORING}'"
    )
    op.drop_constraint("ck_monitoring_alert_recipient_role", MONITORING_RECIPIENT_TABLE, type_="check")

    bind = op.get_bind()
    for name in (FAILURE_STAGE_ENUM, SEVERITY_ENUM, THRESHOLD_UNIT_ENUM):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
