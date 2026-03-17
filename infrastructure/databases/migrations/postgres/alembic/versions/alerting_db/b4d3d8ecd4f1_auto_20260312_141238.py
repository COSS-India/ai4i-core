"""auto_20260312_141238 — correct alerting schema (runs after 37a8d2ea829f)

Revision ID: b4d3d8ecd4f1
Revises: 37a8d2ea829f
Create Date: 2026-03-12 14:12:41.145605

This migration creates the correct alerting_db tables. 37a8d2ea829f is a no-op
for compatibility with environments that already have that revision in alembic_version.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b4d3d8ecd4f1'
down_revision: Union[str, None] = '37a8d2ea829f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('alert_config_audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization', sa.String(length=100), nullable=True),
    sa.Column('table_name', sa.String(length=50), nullable=False),
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('operation', sa.String(length=20), nullable=False),
    sa.Column('changed_by', sa.String(length=100), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('before_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('change_description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_log_changed_at', 'alert_config_audit_log', ['changed_at'], unique=False)
    op.create_index('idx_audit_log_changed_by', 'alert_config_audit_log', ['changed_by'], unique=False)
    op.create_index('idx_audit_log_organization', 'alert_config_audit_log', ['organization'], unique=False)
    op.create_index('idx_audit_log_table_record', 'alert_config_audit_log', ['table_name', 'record_id'], unique=False)
    op.create_table('alert_definitions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('promql_expr', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=50), server_default='application', nullable=False),
    sa.Column('sub_category', sa.String(length=100), nullable=True),
    sa.Column('signal', sa.String(length=100), nullable=True),
    sa.Column('signal_metric', sa.String(length=100), nullable=True),
    sa.Column('condition_operator', sa.String(length=10), nullable=True),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('urgency', sa.String(length=20), server_default='medium', nullable=True),
    sa.Column('alert_type', sa.String(length=50), nullable=True),
    sa.Column('scope', sa.String(length=50), nullable=True),
    sa.Column('service', sa.ARRAY(sa.Text()), nullable=True),
    sa.Column('evaluation_interval', sa.String(length=20), server_default='30s', nullable=True),
    sa.Column('for_duration', sa.String(length=20), server_default='5m', nullable=True),
    sa.Column('threshold_value', sa.Float(), nullable=True),
    sa.Column('threshold_unit', sa.String(length=50), nullable=True),
    sa.Column('enabled', sa.Boolean(), server_default='true', nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('created_by', sa.String(length=100), nullable=True),
    sa.Column('updated_by', sa.String(length=100), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', name='unique_alert_name')
    )
    op.create_index('idx_alert_definitions_category', 'alert_definitions', ['category'], unique=False)
    op.create_index('idx_alert_definitions_enabled', 'alert_definitions', ['enabled'], unique=False)
    op.create_index('idx_alert_definitions_organization', 'alert_definitions', ['organization'], unique=False)
    op.create_index('idx_alert_definitions_organization_enabled', 'alert_definitions', ['organization', 'enabled'], unique=False)
    op.create_index('idx_alert_definitions_severity', 'alert_definitions', ['severity'], unique=False)
    op.create_table('alert_history',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('alert_name', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='firing', nullable=False),
    sa.Column('receiver', sa.String(length=255), nullable=False),
    sa.Column('notified_display', sa.String(length=500), nullable=True),
    sa.Column('tenant', sa.String(length=255), nullable=True),
    sa.Column('organization', sa.String(length=255), nullable=True),
    sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('annotations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('fingerprint', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_alert_history_alert_name', 'alert_history', ['alert_name'], unique=False)
    op.create_index('idx_alert_history_category', 'alert_history', ['category'], unique=False)
    op.create_index('idx_alert_history_severity', 'alert_history', ['severity'], unique=False)
    op.create_index('idx_alert_history_tenant', 'alert_history', ['tenant'], unique=False)
    op.create_index('idx_alert_history_triggered_at', 'alert_history', [sa.literal_column('triggered_at DESC')], unique=False)
    op.create_table('notification_receivers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization', sa.String(length=100), nullable=False),
    sa.Column('receiver_name', sa.String(length=255), nullable=False),
    sa.Column('rule_name', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=50), server_default='application', nullable=False),
    sa.Column('severity', sa.String(length=20), server_default='warning', nullable=False),
    sa.Column('email_to', sa.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('rbac_role', sa.String(length=50), nullable=True),
    sa.Column('alert_names', sa.ARRAY(sa.Text()), nullable=True),
    sa.Column('tenant', sa.String(length=255), nullable=True),
    sa.Column('email_subject_template', sa.Text(), nullable=True),
    sa.Column('email_body_template', sa.Text(), nullable=True),
    sa.Column('enabled', sa.Boolean(), server_default='true', nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('created_by', sa.String(length=100), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization', 'receiver_name', name='unique_organization_receiver_name')
    )
    op.create_index('idx_notification_receivers_category', 'notification_receivers', ['category'], unique=False)
    op.create_index('idx_notification_receivers_enabled', 'notification_receivers', ['enabled'], unique=False)
    op.create_index('idx_notification_receivers_organization', 'notification_receivers', ['organization'], unique=False)
    op.create_index('idx_notification_receivers_severity', 'notification_receivers', ['severity'], unique=False)
    op.create_table('alert_annotations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('alert_definition_id', sa.Integer(), nullable=False),
    sa.Column('annotation_key', sa.String(length=50), nullable=False),
    sa.Column('annotation_value', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['alert_definition_id'], ['alert_definitions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('alert_definition_id', 'annotation_key', name='unique_alert_annotation_key')
    )
    op.create_index('idx_alert_annotations_alert_def_id', 'alert_annotations', ['alert_definition_id'], unique=False)
    op.create_table('routing_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization', sa.String(length=100), nullable=False),
    sa.Column('rule_name', sa.String(length=255), nullable=False),
    sa.Column('receiver_id', sa.Integer(), nullable=False),
    sa.Column('match_severity', sa.String(length=20), nullable=True),
    sa.Column('match_category', sa.String(length=50), nullable=True),
    sa.Column('match_alert_type', sa.String(length=50), nullable=True),
    sa.Column('match_alert_names', sa.ARRAY(sa.Text()), nullable=True),
    sa.Column('match_tenant_id', sa.String(length=255), nullable=True),
    sa.Column('group_by', sa.ARRAY(sa.Text()), nullable=True),
    sa.Column('group_wait', sa.String(length=20), server_default='10s', nullable=True),
    sa.Column('group_interval', sa.String(length=20), server_default='10s', nullable=True),
    sa.Column('repeat_interval', sa.String(length=20), server_default='12h', nullable=True),
    sa.Column('continue_routing', sa.Boolean(), server_default='false', nullable=True),
    sa.Column('priority', sa.Integer(), server_default='100', nullable=True),
    sa.Column('enabled', sa.Boolean(), server_default='true', nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('created_by', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['receiver_id'], ['notification_receivers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization', 'rule_name', name='unique_organization_rule_name')
    )
    op.create_index('idx_routing_rules_enabled', 'routing_rules', ['enabled'], unique=False)
    op.create_index('idx_routing_rules_match_category', 'routing_rules', ['match_category'], unique=False)
    op.create_index('idx_routing_rules_match_severity', 'routing_rules', ['match_severity'], unique=False)
    op.create_index('idx_routing_rules_organization', 'routing_rules', ['organization'], unique=False)
    op.create_index('idx_routing_rules_priority', 'routing_rules', ['priority'], unique=False)
    op.create_index('idx_routing_rules_receiver_id', 'routing_rules', ['receiver_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_routing_rules_receiver_id', table_name='routing_rules')
    op.drop_index('idx_routing_rules_priority', table_name='routing_rules')
    op.drop_index('idx_routing_rules_organization', table_name='routing_rules')
    op.drop_index('idx_routing_rules_match_severity', table_name='routing_rules')
    op.drop_index('idx_routing_rules_match_category', table_name='routing_rules')
    op.drop_index('idx_routing_rules_enabled', table_name='routing_rules')
    op.drop_table('routing_rules')
    op.drop_index('idx_alert_annotations_alert_def_id', table_name='alert_annotations')
    op.drop_table('alert_annotations')
    op.drop_index('idx_notification_receivers_severity', table_name='notification_receivers')
    op.drop_index('idx_notification_receivers_organization', table_name='notification_receivers')
    op.drop_index('idx_notification_receivers_enabled', table_name='notification_receivers')
    op.drop_index('idx_notification_receivers_category', table_name='notification_receivers')
    op.drop_table('notification_receivers')
    op.drop_index('idx_alert_history_triggered_at', table_name='alert_history')
    op.drop_index('idx_alert_history_tenant', table_name='alert_history')
    op.drop_index('idx_alert_history_severity', table_name='alert_history')
    op.drop_index('idx_alert_history_category', table_name='alert_history')
    op.drop_index('idx_alert_history_alert_name', table_name='alert_history')
    op.drop_table('alert_history')
    op.drop_index('idx_alert_definitions_severity', table_name='alert_definitions')
    op.drop_index('idx_alert_definitions_organization_enabled', table_name='alert_definitions')
    op.drop_index('idx_alert_definitions_organization', table_name='alert_definitions')
    op.drop_index('idx_alert_definitions_enabled', table_name='alert_definitions')
    op.drop_index('idx_alert_definitions_category', table_name='alert_definitions')
    op.drop_table('alert_definitions')
    op.drop_index('idx_audit_log_table_record', table_name='alert_config_audit_log')
    op.drop_index('idx_audit_log_organization', table_name='alert_config_audit_log')
    op.drop_index('idx_audit_log_changed_by', table_name='alert_config_audit_log')
    op.drop_index('idx_audit_log_changed_at', table_name='alert_config_audit_log')
    op.drop_table('alert_config_audit_log')
