"""seed_default_data

Revision ID: 2362774ac241
Revises: b66dd69a00df
Create Date: 2026-05-18 15:50:05.077932

"""
import os
import secrets
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2362774ac241'
down_revision: Union[str, None] = 'b66dd69a00df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    from passlib.context import CryptContext
    _ctx = CryptContext(schemes=["argon2"], default="argon2")

    conn = op.get_bind()

    roles = [
        ("ADMIN",        "Administrator with full system access"),
        ("USER",         "Regular user with standard permissions"),
        ("GUEST",        "Guest: own profile read + ASR/NMT/TTS inference"),
        ("MODERATOR",    "Moderator with elevated management permissions"),
        ("TENANT ADMIN", "Tenant administrator with tenant-scoped management permissions"),
    ]

    permissions = [
        (1,   "admin",                          "admin",              "admin"),
        (11,  "users.create",                   "users",              "create"),
        (12,  "users.read",                     "users",              "read"),
        (13,  "users.update",                   "users",              "update"),
        (14,  "users.delete",                   "users",              "delete"),
        (15,  "users.profile.read",             "users.profile",      "read"),
        (16,  "users.profile.update",           "users.profile",      "update"),
        (17,  "users.password.change",          "users.password",     "change"),
        (20,  "roles.read",                     "roles",              "read"),
        (21,  "roles.assign",                   "roles",              "assign"),
        (22,  "roles.remove",                   "roles",              "remove"),
        (23,  "permissions.read",               "permissions",        "read"),
        (30,  "apiKey.create",                  "apiKey",             "create"),
        (31,  "apiKey.read",                    "apiKey",             "read"),
        (32,  "apiKey.update",                  "apiKey",             "update"),
        (33,  "apiKey.delete",                  "apiKey",             "delete"),
        (34,  "apiKey.read.all",                "apiKey",             "read.all"),
        (40,  "tenant.create",                  "tenant",             "create"),
        (41,  "tenant.read",                    "tenant",             "read"),
        (42,  "tenant.update",                  "tenant",             "update"),
        (44,  "tenant.users.read",              "tenant.users",       "read"),
        (45,  "tenant.users.create",            "tenant.users",       "create"),
        (46,  "tenant.users.update",            "tenant.users",       "update"),
        (47,  "tenant.users.delete",            "tenant.users",       "delete"),
        (50,  "service.create",                 "service",            "create"),
        (51,  "service.read",                   "service",            "read"),
        (52,  "service.update",                 "service",            "update"),
        (53,  "service.delete",                 "service",            "delete"),
        (54,  "model.create",                   "model",              "create"),
        (55,  "model.read",                     "model",              "read"),
        (56,  "model.update",                   "model",              "update"),
        (57,  "model.delete",                   "model",              "delete"),
        (60,  "nmt.inference",                  "nmt",                "inference"),
        (61,  "asr.inference",                  "asr",                "inference"),
        (62,  "tts.inference",                  "tts",                "inference"),
        (63,  "llm.inference",                  "llm",                "inference"),
        (64,  "ner.inference",                  "ner",                "inference"),
        (65,  "ocr.inference",                  "ocr",                "inference"),
        (66,  "transliteration.inference",      "transliteration",    "inference"),
        (67,  "language-detection.inference",   "language-detection", "inference"),
        (68,  "language-diarization.inference", "language-diarization", "inference"),
        (69,  "speaker-diarization.inference",  "speaker-diarization", "inference"),
        (70,  "audio-lang-detection.inference", "audio-lang-detection", "inference"),
        (71,  "pipeline.inference",             "pipeline",           "inference"),
        (80,  "nmt.read",                       "nmt",                "read"),
        (81,  "asr.read",                       "asr",                "read"),
        (82,  "tts.read",                       "tts",                "read"),
        (83,  "llm.read",                       "llm",                "read"),
        (84,  "transliteration.read",           "transliteration",    "read"),
        (85,  "language-detection.read",        "language-detection", "read"),
        (90,  "pii_guard.inference",            "pii_guard",          "inference"),
        (91,  "pii_guard.admin",                "pii_guard",          "admin"),
        (92,  "pii_guard.audit.read",           "pii_guard.audit",    "read"),
        (100, "policies.read",                  "policies",           "read"),
        (101, "policies.create",                "policies",           "create"),
        (102, "policies.update",                "policies",           "update"),
        (103, "policies.delete",                "policies",           "delete"),
        (104, "policies.assign",                "policies",           "assign"),
        (105, "pii_types.read",                 "pii_types",          "read"),
        (106, "pii_types.create",               "pii_types",          "create"),
        (107, "pii_types.update",               "pii_types",          "update"),
        (108, "pii_types.delete",               "pii_types",          "delete"),
        (109, "audit_logs.read",                "audit_logs",         "read"),
        (110, "metrics.read",                   "metrics",            "read"),
        (111, "metrics.export",                 "metrics",            "export"),
        (112, "dashboards.read",                "dashboards",         "read"),
        (113, "dashboards.create",              "dashboards",         "create"),
        (114, "dashboards.update",              "dashboards",         "update"),
        (115, "dashboards.delete",              "dashboards",         "delete"),
        (116, "alerts.read",                    "alerts",             "read"),
        (117, "alerts.create",                  "alerts",             "create"),
        (118, "alerts.update",                  "alerts",             "update"),
        (119, "alerts.delete",                  "alerts",             "delete"),
        (120, "configs.read",                   "configs",            "read"),
        (121, "configs.create",                 "configs",            "create"),
        (122, "configs.update",                 "configs",            "update"),
        (123, "configs.delete",                 "configs",            "delete"),
        (130, "logs.read",                      "logs",               "read"),
        (131, "traces.read",                    "traces",             "read"),
        (132, "telemetry.write",                "telemetry",          "write"),
    ]

    # Delete role_permission first (FK to both roles and permissions)
    conn.execute(sa.text("DELETE FROM role_permission"))
    conn.execute(sa.text("DELETE FROM permissions"))

    # Upsert roles
    for name, description in roles:
        conn.execute(
            sa.text("""
                INSERT INTO roles (name, description, created_by)
                VALUES (:name, :description, :created_by)
                ON CONFLICT (name) DO UPDATE
                  SET description = EXCLUDED.description
            """),
            {"name": name, "description": description, "created_by": SEEDER_ID},
        )

    # Insert permissions with explicit IDs
    for pid, name, resource, action in permissions:
        conn.execute(
            sa.text("""
                INSERT INTO permissions (id, name, resource, action, created_by)
                VALUES (:id, :name, :resource, :action, :created_by)
            """),
            {"id": pid, "name": name, "resource": resource, "action": action, "created_by": SEEDER_ID},
        )

    max_id = max(p[0] for p in permissions)
    conn.execute(sa.text(f"SELECT setval(pg_get_serial_sequence('permissions', 'id'), {max_id})"))

    # ADMIN: every permission
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r CROSS JOIN permissions p
        WHERE r.name = 'ADMIN'
    """))

    # USER: profile + inference
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON p.name IN (
          'users.profile.read',
          'users.profile.update',
          'users.password.change',
          'apiKey.create',
          'apiKey.read',
          'apiKey.update',
          'apiKey.delete',
          'service.read',
          'model.read',
          'asr.inference',
          'audio-lang-detection.inference',
          'language-detection.inference',
          'language-diarization.inference',
          'llm.inference',
          'ner.inference',
          'nmt.inference',
          'ocr.inference',
          'pipeline.inference',
          'pii_guard.inference',
          'speaker-diarization.inference',
          'transliteration.inference',
          'tts.inference'
        )
        WHERE r.name = 'USER'
    """))

    # GUEST: minimal
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON p.name IN (
          'users.profile.read',
          'roles.read',
          'service.read',
          'asr.inference',
          'nmt.inference',
          'tts.inference'
        )
        WHERE r.name = 'GUEST'
    """))

    # MODERATOR
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON p.name IN (
          'users.create', 'users.read', 'users.update', 'users.delete',
          'users.profile.read', 'users.profile.update', 'users.password.change',
          'permissions.read',
          'apiKey.create', 'apiKey.read', 'apiKey.update', 'apiKey.delete',
          'service.create', 'service.read', 'service.update', 'service.delete',
          'model.create', 'model.read', 'model.update', 'model.delete',
          'asr.inference', 'audio-lang-detection.inference', 'language-detection.inference',
          'language-diarization.inference', 'llm.inference', 'ner.inference',
          'nmt.inference', 'ocr.inference', 'pipeline.inference',
          'pii_guard.inference', 'speaker-diarization.inference',
          'transliteration.inference', 'tts.inference',
          'configs.read', 'configs.create', 'configs.update', 'configs.delete',
          'metrics.read', 'metrics.export',
          'alerts.read', 'alerts.create', 'alerts.update', 'alerts.delete',
          'dashboards.read', 'dashboards.create', 'dashboards.update', 'dashboards.delete'
        )
        WHERE r.name = 'MODERATOR'
    """))

    # TENANT ADMIN
    conn.execute(sa.text(f"""
        INSERT INTO role_permission (role_id, permission_id, created_by)
        SELECT r.id, p.id, '{SEEDER_ID}'
        FROM roles r
        JOIN permissions p ON p.name IN (
          'users.create', 'users.read', 'users.update',
          'users.profile.read', 'users.profile.update', 'users.password.change',
          'roles.read', 'roles.assign', 'roles.remove', 'permissions.read',
          'apiKey.create', 'apiKey.read', 'apiKey.update', 'apiKey.delete',
          'service.read', 'model.read', 'pii_guard.admin',
          'asr.inference', 'audio-lang-detection.inference', 'language-detection.inference',
          'language-diarization.inference', 'llm.inference', 'ner.inference',
          'nmt.inference', 'ocr.inference', 'pipeline.inference',
          'speaker-diarization.inference', 'transliteration.inference', 'tts.inference',
          'tenant.read', 'tenant.users.read', 'tenant.users.create',
          'tenant.users.update', 'tenant.users.delete'
        )
        WHERE r.name = 'TENANT ADMIN'
    """))

    # Default tenant
    org     = (os.getenv("DEFAULT_TENANT_ORG") or "default organisation").strip()
    contact = (os.getenv("DEFAULT_TENANT_CONTACT") or "default").strip()
    email   = (os.getenv("DEFAULT_TENANT_EMAIL") or "admin@ai4inclusion.org").strip()

    existing = conn.execute(
        sa.text("SELECT id FROM tenants WHERE organisation = :org LIMIT 1"),
        {"org": org},
    ).fetchone()

    if existing:
        conn.execute(
            sa.text("""
                UPDATE tenants
                SET name = :contact, email = :email, status = 'activated',
                    updated_by = :seeder_id
                WHERE organisation = :org
            """),
            {"contact": contact, "email": email, "org": org, "seeder_id": SEEDER_ID},
        )
    else:
        conn.execute(
            sa.text("""
                INSERT INTO tenants (name, organisation, email, status, created_by)
                VALUES (:contact, :org, :email, 'activated', :seeder_id)
            """),
            {"contact": contact, "org": org, "email": email, "seeder_id": SEEDER_ID},
        )

    tenant_row = conn.execute(
        sa.text("SELECT id FROM tenants WHERE organisation = :org LIMIT 1"),
        {"org": org},
    ).fetchone()
    tenant_id = tenant_row[0] if tenant_row else None

    # Admin user
    admin_password = os.getenv("ADMIN_DEFAULT_PASSWORD", "ADMIN_PASSWORD")
    admin_email    = "admin@ai4inclusion.org"
    admin_salt     = secrets.token_hex(16)
    admin_hash     = _ctx.hash(admin_password + admin_salt)
    admin_user_id  = str(uuid.uuid4())

    conn.execute(
        sa.text("""
            INSERT INTO users (
                id, email, username, full_name, is_active, tenant_id,
                timezone, is_delete, is_tenant_active, creation_type, created_by
            ) VALUES (
                :user_id, :email, 'admin', 'Default Admin', true, :tenant_id,
                'UTC', false, true, 'default', :created_by
            )
            ON CONFLICT (email) DO UPDATE
            SET username = EXCLUDED.username, full_name = EXCLUDED.full_name,
                is_active = EXCLUDED.is_active, tenant_id = EXCLUDED.tenant_id,
                timezone = EXCLUDED.timezone, is_delete = EXCLUDED.is_delete,
                is_tenant_active = EXCLUDED.is_tenant_active
        """),
        {"user_id": admin_user_id, "email": admin_email, "tenant_id": tenant_id, "created_by": SEEDER_ID},
    )
    actual_admin_row = conn.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": admin_email},
    ).fetchone()
    actual_admin_id = str(actual_admin_row[0])

    conn.execute(
        sa.text("""
            INSERT INTO user_credentials (user_id, password_hash, password_salt, created_by)
            VALUES (:user_id, :password_hash, :password_salt, :created_by)
            ON CONFLICT (user_id) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                password_salt = EXCLUDED.password_salt
        """),
        {"user_id": actual_admin_id, "password_hash": admin_hash, "password_salt": admin_salt, "created_by": SEEDER_ID},
    )
    conn.execute(
        sa.text(f"""
            INSERT INTO user_role (user_id, role_id, created_by)
            SELECT u.id, r.id, '{SEEDER_ID}'
            FROM users u JOIN roles r ON r.name = 'ADMIN'
            WHERE u.email = :email
              AND NOT EXISTS (
                  SELECT 1 FROM user_role ur
                  WHERE ur.user_id = u.id AND ur.role_id = r.id
              )
        """),
        {"email": admin_email},
    )

    # Guest user
    guest_email    = (os.getenv("GUEST_EMAIL") or "guest@ai4inclusion.org").strip()
    guest_password = os.getenv("GUEST_PASSWORD", "GUEST_PASSWORD")
    guest_salt     = secrets.token_hex(16)
    guest_hash     = _ctx.hash(guest_password + guest_salt)
    guest_user_id  = str(uuid.uuid4())

    conn.execute(
        sa.text("""
            INSERT INTO users (
                id, email, username, full_name, is_active, tenant_id,
                timezone, is_delete, is_tenant_active, creation_type, created_by
            ) VALUES (
                :user_id, :email, 'guest', 'Default Guest', true, :tenant_id,
                'UTC', false, true, 'default', :created_by
            )
            ON CONFLICT (email) DO UPDATE
            SET username = EXCLUDED.username, full_name = EXCLUDED.full_name,
                is_active = EXCLUDED.is_active, tenant_id = EXCLUDED.tenant_id,
                timezone = EXCLUDED.timezone, is_delete = EXCLUDED.is_delete,
                is_tenant_active = EXCLUDED.is_tenant_active
        """),
        {"user_id": guest_user_id, "email": guest_email, "tenant_id": tenant_id, "created_by": SEEDER_ID},
    )
    actual_guest_row = conn.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": guest_email},
    ).fetchone()
    actual_guest_id = str(actual_guest_row[0])

    conn.execute(
        sa.text("""
            INSERT INTO user_credentials (user_id, password_hash, password_salt, created_by)
            VALUES (:user_id, :password_hash, :password_salt, :created_by)
            ON CONFLICT (user_id) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                password_salt = EXCLUDED.password_salt
        """),
        {"user_id": actual_guest_id, "password_hash": guest_hash, "password_salt": guest_salt, "created_by": SEEDER_ID},
    )
    conn.execute(
        sa.text(f"""
            INSERT INTO user_role (user_id, role_id, created_by)
            SELECT u.id, r.id, '{SEEDER_ID}'
            FROM users u JOIN roles r ON r.name = 'GUEST'
            WHERE u.email = :email
              AND NOT EXISTS (
                  SELECT 1 FROM user_role ur
                  WHERE ur.user_id = u.id AND ur.role_id = r.id
              )
        """),
        {"email": guest_email},
    )


def downgrade() -> None:
    conn = op.get_bind()
    seeded_users = conn.execute(
        sa.text("SELECT id FROM users WHERE created_by = :sid"),
        {"sid": SEEDER_ID}
    ).fetchall()
    seeded_ids = [str(r[0]) for r in seeded_users]
    if seeded_ids:
        id_list = ", ".join(f"'{uid}'" for uid in seeded_ids)
        conn.execute(sa.text(f"DELETE FROM user_role WHERE user_id IN ({id_list})"))
        conn.execute(sa.text(f"DELETE FROM user_credentials WHERE user_id IN ({id_list})"))
        conn.execute(sa.text(f"DELETE FROM users WHERE id IN ({id_list})"))
    conn.execute(sa.text(f"DELETE FROM tenants WHERE created_by = '{SEEDER_ID}'"))
    conn.execute(sa.text("DELETE FROM role_permission"))
    conn.execute(sa.text("DELETE FROM permissions"))
