"""auto_20260425_103736

Revision ID: 03c373bdd881
Revises: 
Create Date: 2026-04-25 10:37:37.324405

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '03c373bdd881'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reference-only enum: create_type=False means SQLAlchemy never auto-issues
# CREATE/DROP TYPE.  We manage the type lifecycle ourselves with op.execute().
_PERMISSION_NAME_ENUM_REF = postgresql.ENUM(
    'users.create', 'users.read', 'users.update', 'users.delete',
    'configs.create', 'configs.read', 'configs.update', 'configs.delete',
    'metrics.read', 'metrics.export',
    'alerts.create', 'alerts.read', 'alerts.update', 'alerts.delete',
    'dashboards.create', 'dashboards.read', 'dashboards.update', 'dashboards.delete',
    'apiKey.create', 'apiKey.read', 'apiKey.delete', 'apiKey.update',
    'service.create', 'service.delete', 'service.update', 'service.read',
    'model.create', 'model.read', 'model.update', 'model.delete',
    'model.publish', 'model.unpublish',
    'roles.assign', 'roles.remove', 'roles.read',
    'asr.inference', 'asr.read',
    'tts.inference', 'tts.read',
    'nmt.inference', 'nmt.read',
    'audio-lang-detection.read', 'audio-lang-detection.inference',
    'language-detection.read', 'language-detection.inference',
    'language-diarization.read', 'language-diarization.inference',
    'ner.inference',
    'ocr.read', 'ocr.inference',
    'speaker-diarization.read', 'speaker-diarization.inference',
    'transliteration.read', 'transliteration.inference',
    'pipeline.read', 'pipeline.inference',
    'llm.read', 'llm.inference',
    'model-management.read', 'model-management.inference',
    'logs.read', 'traces.read',
    'tenant.create', 'tenant.read', 'tenant.update',
    'tenant.users.read', 'tenant.users.update',
    'pii_guard.inference', 'pii_guard.admin',
    name='permission_name_enum',
    create_type=False,
)

_PERMISSION_VALUES = (
    "'users.create','users.read','users.update','users.delete',"
    "'configs.create','configs.read','configs.update','configs.delete',"
    "'metrics.read','metrics.export',"
    "'alerts.create','alerts.read','alerts.update','alerts.delete',"
    "'dashboards.create','dashboards.read','dashboards.update','dashboards.delete',"
    "'apiKey.create','apiKey.read','apiKey.delete','apiKey.update',"
    "'service.create','service.delete','service.update','service.read',"
    "'model.create','model.read','model.update','model.delete',"
    "'model.publish','model.unpublish',"
    "'roles.assign','roles.remove','roles.read',"
    "'asr.inference','asr.read',"
    "'tts.inference','tts.read',"
    "'nmt.inference','nmt.read',"
    "'audio-lang-detection.read','audio-lang-detection.inference',"
    "'language-detection.read','language-detection.inference',"
    "'language-diarization.read','language-diarization.inference',"
    "'ner.inference',"
    "'ocr.read','ocr.inference',"
    "'speaker-diarization.read','speaker-diarization.inference',"
    "'transliteration.read','transliteration.inference',"
    "'pipeline.read','pipeline.inference',"
    "'llm.read','llm.inference',"
    "'model-management.read','model-management.inference',"
    "'logs.read','traces.read',"
    "'tenant.create','tenant.read','tenant.update',"
    "'tenant.users.read','tenant.users.update',"
    "'pii_guard.inference','pii_guard.admin'"
)


def upgrade() -> None:
    # ── audit ─────────────────────────────────────────────────────────────────
    op.create_table(
        'audit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.Enum('USER', 'ROLE', 'TENANT', 'API_KEY', name='audit_entity_type_enum'), nullable=False),
        sa.Column('entity_action', sa.Enum('CREATE', 'UPDATE', 'DELETE', name='audit_entity_action_enum'), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_entity_action'), 'audit', ['entity_action'], unique=False)
    op.create_index(op.f('ix_audit_entity_type'), 'audit', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_id'), 'audit', ['id'], unique=False)
    op.create_index(op.f('ix_audit_subject'), 'audit', ['subject'], unique=False)

    # ── permissions ───────────────────────────────────────────────────────────
    # Create the PostgreSQL enum type explicitly before the table so that
    # SQLAlchemy's auto-create event never fires a duplicate CREATE TYPE.
    op.execute(sa.text(
        f"CREATE TYPE permission_name_enum AS ENUM ({_PERMISSION_VALUES})"
    ))
    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', _PERMISSION_NAME_ENUM_REF, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_permissions_id'), 'permissions', ['id'], unique=False)
    op.create_index(op.f('ix_permissions_name'), 'permissions', ['name'], unique=True)

    # ── roles ─────────────────────────────────────────────────────────────────
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_roles_id'), 'roles', ['id'], unique=False)
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)

    # ── tenants ───────────────────────────────────────────────────────────────
    # PK is auto-increment Integer; contact_name renamed to name.
    op.create_table(
        'tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('organisation', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=True),
        sa.Column('status', sa.Enum('activated', 'deactivated', 'suspended', name='tenant_status_enum'), server_default='activated', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tenants_id'), 'tenants', ['id'], unique=False)

    # ── token_verification ────────────────────────────────────────────────────
    # token column is TEXT from the start (avoids the separate widening migration).
    op.create_table(
        'token_verification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_token_verification_id'), 'token_verification', ['id'], unique=False)
    op.create_index(op.f('ix_token_verification_token'), 'token_verification', ['token'], unique=True)

    # ── role_permission ───────────────────────────────────────────────────────
    op.create_table(
        'role_permission',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_role_permission_id'), 'role_permission', ['id'], unique=False)
    op.create_index(op.f('ix_role_permission_permission_id'), 'role_permission', ['permission_id'], unique=False)
    op.create_index(op.f('ix_role_permission_role_id'), 'role_permission', ['role_id'], unique=False)

    # ── users ─────────────────────────────────────────────────────────────────
    # PK is UUID (id); tenant_id is Integer FK to tenants.id.
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('avatar_url', sa.String(length=500), nullable=True),
        sa.Column('phone_number', sa.String(length=20), nullable=True),
        sa.Column('timezone', sa.String(length=50), server_default='UTC', nullable=True),
        sa.Column('is_delete', sa.Boolean(), nullable=True),
        sa.Column('is_tenant_active', sa.Boolean(), nullable=True),
        sa.Column('creation_type', sa.Enum('default', 'google', name='creation_type_enum'), server_default='default', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # ── api_key ───────────────────────────────────────────────────────────────
    # PK is id (Integer); api_key is 32-char hex; includes expires_at from start.
    op.create_table(
        'api_key',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key_name', sa.String(length=100), nullable=False),
        sa.Column('api_key', sa.String(length=32), nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_api_key_api_key'), 'api_key', ['api_key'], unique=True)
    op.create_index(op.f('ix_api_key_id'), 'api_key', ['id'], unique=False)
    op.create_index(op.f('ix_api_key_user_id'), 'api_key', ['user_id'], unique=False)

    # ── refresh ───────────────────────────────────────────────────────────────
    # id is Integer PK; user_id is unique UUID FK.
    op.create_table(
        'refresh',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('refresh_token', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_refresh_id'), 'refresh', ['id'], unique=False)
    op.create_index(op.f('ix_refresh_refresh_token'), 'refresh', ['refresh_token'], unique=True)
    op.create_index(op.f('ix_refresh_user_id'), 'refresh', ['user_id'], unique=True)

    # ── user_credentials ──────────────────────────────────────────────────────
    # id is Integer PK; user_id is unique UUID FK.
    op.create_table(
        'user_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('password_salt', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_credentials_id'), 'user_credentials', ['id'], unique=False)
    op.create_index(op.f('ix_user_credentials_user_id'), 'user_credentials', ['user_id'], unique=True)

    # ── user_role ─────────────────────────────────────────────────────────────
    op.create_table(
        'user_role',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_role_id'), 'user_role', ['id'], unique=False)
    op.create_index(op.f('ix_user_role_role_id'), 'user_role', ['role_id'], unique=False)
    op.create_index(op.f('ix_user_role_user_id'), 'user_role', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_role_user_id'), table_name='user_role')
    op.drop_index(op.f('ix_user_role_role_id'), table_name='user_role')
    op.drop_index(op.f('ix_user_role_id'), table_name='user_role')
    op.drop_table('user_role')

    op.drop_index(op.f('ix_user_credentials_user_id'), table_name='user_credentials')
    op.drop_index(op.f('ix_user_credentials_id'), table_name='user_credentials')
    op.drop_table('user_credentials')

    op.drop_index(op.f('ix_refresh_user_id'), table_name='refresh')
    op.drop_index(op.f('ix_refresh_refresh_token'), table_name='refresh')
    op.drop_index(op.f('ix_refresh_id'), table_name='refresh')
    op.drop_table('refresh')

    op.drop_index(op.f('ix_api_key_user_id'), table_name='api_key')
    op.drop_index(op.f('ix_api_key_id'), table_name='api_key')
    op.drop_index(op.f('ix_api_key_api_key'), table_name='api_key')
    op.drop_table('api_key')

    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.execute(sa.text("DROP TYPE IF EXISTS creation_type_enum"))

    op.drop_index(op.f('ix_role_permission_role_id'), table_name='role_permission')
    op.drop_index(op.f('ix_role_permission_permission_id'), table_name='role_permission')
    op.drop_index(op.f('ix_role_permission_id'), table_name='role_permission')
    op.drop_table('role_permission')

    op.drop_index(op.f('ix_token_verification_token'), table_name='token_verification')
    op.drop_index(op.f('ix_token_verification_id'), table_name='token_verification')
    op.drop_table('token_verification')

    op.drop_index(op.f('ix_tenants_id'), table_name='tenants')
    op.drop_table('tenants')
    op.execute(sa.text("DROP TYPE IF EXISTS tenant_status_enum"))

    op.drop_index(op.f('ix_roles_name'), table_name='roles')
    op.drop_index(op.f('ix_roles_id'), table_name='roles')
    op.drop_table('roles')

    op.drop_index(op.f('ix_permissions_name'), table_name='permissions')
    op.drop_index(op.f('ix_permissions_id'), table_name='permissions')
    op.drop_table('permissions')
    op.execute(sa.text("DROP TYPE IF EXISTS permission_name_enum"))

    op.drop_index(op.f('ix_audit_subject'), table_name='audit')
    op.drop_index(op.f('ix_audit_id'), table_name='audit')
    op.drop_index(op.f('ix_audit_entity_type'), table_name='audit')
    op.drop_index(op.f('ix_audit_entity_action'), table_name='audit')
    op.drop_table('audit')
    op.execute(sa.text("DROP TYPE IF EXISTS audit_entity_type_enum"))
    op.execute(sa.text("DROP TYPE IF EXISTS audit_entity_action_enum"))
