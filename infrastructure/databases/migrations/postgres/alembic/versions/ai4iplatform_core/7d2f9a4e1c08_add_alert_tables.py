"""add alert tables

Creates the alert-management tables in ai4iplatform_core (migrated out of the
standalone alerting_db). Schema matches services/platform-core-service/app/models/
alert_management/* — with `organization` columns dropped and the audit-log table
omitted per the alert→platform-core migration plan.

Revision ID: 7d2f9a4e1c08
Revises: 31d7bc3f4379
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7d2f9a4e1c08'
down_revision: Union[str, None] = '31d7bc3f4379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── alert_definitions ──────────────────────────────────────────────────
    op.create_table(
        'alert_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('promql_expr', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False, server_default='application'),
        sa.Column('sub_category', sa.String(length=100), nullable=True),
        sa.Column('signal', sa.String(length=100), nullable=True),
        sa.Column('signal_metric', sa.String(length=100), nullable=True),
        sa.Column('condition_operator', sa.String(length=10), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('urgency', sa.String(length=20), nullable=True, server_default='medium'),
        sa.Column('alert_type', sa.String(length=50), nullable=True),
        sa.Column('scope', sa.String(length=50), nullable=True),
        sa.Column('service', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('evaluation_interval', sa.String(length=20), nullable=True, server_default='30s'),
        sa.Column('for_duration', sa.String(length=20), nullable=True, server_default='5m'),
        sa.Column('threshold_value', sa.Float(), nullable=True),
        sa.Column('threshold_unit', sa.String(length=50), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='unique_alert_name'),
    )
    op.create_index('idx_alert_definitions_enabled', 'alert_definitions', ['enabled'])
    op.create_index('idx_alert_definitions_category', 'alert_definitions', ['category'])
    op.create_index('idx_alert_definitions_severity', 'alert_definitions', ['severity'])

    # ── alert_annotations ──────────────────────────────────────────────────
    op.create_table(
        'alert_annotations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alert_definition_id', sa.Integer(), nullable=False),
        sa.Column('annotation_key', sa.String(length=50), nullable=False),
        sa.Column('annotation_value', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['alert_definition_id'], ['alert_definitions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alert_definition_id', 'annotation_key', name='unique_alert_annotation_key'),
    )
    op.create_index('idx_alert_annotations_alert_def_id', 'alert_annotations', ['alert_definition_id'])

    # ── notification_receivers ─────────────────────────────────────────────
    op.create_table(
        'notification_receivers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('receiver_name', sa.String(length=255), nullable=False),
        sa.Column('rule_name', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False, server_default='application'),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='warning'),
        sa.Column('email_to', postgresql.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('rbac_role', sa.String(length=50), nullable=True),
        sa.Column('alert_names', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('tenant', sa.String(length=255), nullable=True),
        sa.Column('email_subject_template', sa.Text(), nullable=True),
        sa.Column('email_body_template', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('receiver_name', name='unique_receiver_name'),
    )
    op.create_index('idx_notification_receivers_enabled', 'notification_receivers', ['enabled'])
    op.create_index('idx_notification_receivers_category', 'notification_receivers', ['category'])
    op.create_index('idx_notification_receivers_severity', 'notification_receivers', ['severity'])

    # ── routing_rules ──────────────────────────────────────────────────────
    op.create_table(
        'routing_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_name', sa.String(length=255), nullable=False),
        sa.Column('receiver_id', sa.Integer(), nullable=False),
        sa.Column('match_severity', sa.String(length=20), nullable=True),
        sa.Column('match_category', sa.String(length=50), nullable=True),
        sa.Column('match_alert_type', sa.String(length=50), nullable=True),
        sa.Column('match_alert_names', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('match_tenant_id', sa.String(length=255), nullable=True),
        sa.Column('group_by', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('group_wait', sa.String(length=20), nullable=True, server_default='10s'),
        sa.Column('group_interval', sa.String(length=20), nullable=True, server_default='10s'),
        sa.Column('repeat_interval', sa.String(length=20), nullable=True, server_default='12h'),
        sa.Column('continue_routing', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('priority', sa.Integer(), nullable=True, server_default='100'),
        sa.Column('enabled', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['receiver_id'], ['notification_receivers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rule_name', name='unique_rule_name'),
    )
    op.create_index('idx_routing_rules_receiver_id', 'routing_rules', ['receiver_id'])
    op.create_index('idx_routing_rules_enabled', 'routing_rules', ['enabled'])
    op.create_index('idx_routing_rules_priority', 'routing_rules', ['priority'])
    op.create_index('idx_routing_rules_match_severity', 'routing_rules', ['match_severity'])
    op.create_index('idx_routing_rules_match_category', 'routing_rules', ['match_category'])

    # ── alert_history ──────────────────────────────────────────────────────
    op.create_table(
        'alert_history',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('alert_name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='firing'),
        sa.Column('receiver', sa.String(length=255), nullable=False),
        sa.Column('notified_display', sa.String(length=500), nullable=True),
        sa.Column('tenant', sa.String(length=255), nullable=True),
        sa.Column('labels', postgresql.JSONB(), nullable=True),
        sa.Column('annotations', postgresql.JSONB(), nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_alert_history_triggered_at', 'alert_history', [sa.text('triggered_at DESC')])
    op.create_index('idx_alert_history_category', 'alert_history', ['category'])
    op.create_index('idx_alert_history_severity', 'alert_history', ['severity'])
    op.create_index('idx_alert_history_alert_name', 'alert_history', ['alert_name'])
    op.create_index('idx_alert_history_tenant', 'alert_history', ['tenant'])


def downgrade() -> None:
    op.drop_table('alert_history')
    op.drop_table('routing_rules')
    op.drop_table('notification_receivers')
    op.drop_table('alert_annotations')
    op.drop_table('alert_definitions')
