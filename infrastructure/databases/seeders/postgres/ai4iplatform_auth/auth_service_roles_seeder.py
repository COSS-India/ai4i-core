"""
Auth Service Roles, Permissions, and Role-Permissions Seeder (ai4iplatform_auth)

Mirrors auth_roles_permissions_seeder.py for the auth-service database.
Seeds roles, permissions, and role-permission mappings idempotently.

Schema differences vs auth_db:
  - roles PK column is `role_id` (not `id`)
  - permissions PK column is `permission_id` (not `id`)
  - join table is `role_permission` (not `role_permissions`) with no unique
    constraint on (role_id, permission_id) → uses DELETE + INSERT pattern

Rows created by this seeder carry created_by = SEEDER_ID so they can be
distinguished from user-created records.

Runs before tenant and user seeders (filename order: auth_service_r... < auth_service_t/y/z...).
"""
from infrastructure.databases.core.base_seeder import BaseSeeder

# Fixed identity for all rows written by seeders — readable as "seed0000…"
SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


class AuthServiceRolesSeeder(BaseSeeder):
    """Seed default roles, permissions, and role-permissions for ai4iplatform_auth"""

    database = "ai4iplatform_auth"

    def run(self, adapter):
        # ── 1. Roles ──────────────────────────────────────────────────────────
        roles = [
            ("ADMIN", "Administrator with full system access"),
            ("USER", "Regular user with standard permissions"),
            ("GUEST", "Guest user with limited read-only access"),
            ("MODERATOR", "Moderator with elevated permissions"),
            ("TENANT ADMIN", "Tenant administrator with tenant-scoped management permissions"),
        ]
        role_names = [r[0] for r in roles]
        role_names_quoted = "', '".join(role_names)

        # Remove roles that are no longer in the seed list
        adapter.execute(
            f"""
            DELETE FROM role_permission
            WHERE role_id NOT IN (
                SELECT role_id FROM roles WHERE name IN ('{role_names_quoted}')
            )
            """
        )
        adapter.execute(
            f"""
            DELETE FROM roles
            WHERE name NOT IN ('{role_names_quoted}')
            """
        )

        for name, description in roles:
            adapter.execute(
                """
                INSERT INTO roles (name, description, created_by)
                VALUES (:name, :description, :created_by)
                ON CONFLICT (name) DO UPDATE
                  SET description = EXCLUDED.description
                """,
                {"name": name, "description": description, "created_by": SEEDER_ID},
            )
        print(f"    ✓ Seeded {len(roles)} roles in ai4iplatform_auth")

        # ── 2. Permissions ────────────────────────────────────────────────────
        permissions = [
            # User management
            ("users.create", "users", "create"),
            ("users.read",   "users", "read"),
            ("users.update", "users", "update"),
            ("users.delete", "users", "delete"),
            # Configuration
            ("configs.create", "configs", "create"),
            ("configs.read",   "configs", "read"),
            ("configs.update", "configs", "update"),
            ("configs.delete", "configs", "delete"),
            # Metrics
            ("metrics.read",   "metrics", "read"),
            ("metrics.export", "metrics", "export"),
            # Alerts
            ("alerts.create", "alerts", "create"),
            ("alerts.read",   "alerts", "read"),
            ("alerts.update", "alerts", "update"),
            ("alerts.delete", "alerts", "delete"),
            # Dashboards
            ("dashboards.create", "dashboards", "create"),
            ("dashboards.read",   "dashboards", "read"),
            ("dashboards.update", "dashboards", "update"),
            ("dashboards.delete", "dashboards", "delete"),
            # API Key Management
            ("apiKey.create", "apiKey", "create"),
            ("apiKey.read",   "apiKey", "read"),
            ("apiKey.delete", "apiKey", "delete"),
            ("apiKey.update", "apiKey", "update"),
            # Service Management
            ("service.create", "service", "create"),
            ("service.delete", "service", "delete"),
            ("service.update", "service", "update"),
            ("service.read",   "service", "read"),
            # Model Management
            ("model.create",    "model", "create"),
            ("model.read",      "model", "read"),
            ("model.update",    "model", "update"),
            ("model.delete",    "model", "delete"),
            ("model.publish",   "model", "publish"),
            ("model.unpublish", "model", "unpublish"),
            # Role Management
            ("roles.assign", "roles", "assign"),
            ("roles.remove", "roles", "remove"),
            ("roles.read",   "roles", "read"),
            # AI Services
            ("asr.inference", "asr", "inference"),
            ("asr.read",      "asr", "read"),
            ("tts.inference", "tts", "inference"),
            ("tts.read",      "tts", "read"),
            ("nmt.inference", "nmt", "inference"),
            ("nmt.read",      "nmt", "read"),
            ("audio-lang-detection.read",       "audio-lang-detection", "read"),
            ("audio-lang-detection.inference",  "audio-lang-detection", "inference"),
            ("language-detection.read",         "language-detection",   "read"),
            ("language-detection.inference",    "language-detection",   "inference"),
            ("language-diarization.read",       "language-diarization", "read"),
            ("language-diarization.inference",  "language-diarization", "inference"),
            ("ner.inference",                   "ner",                  "inference"),
            ("ocr.read",                        "ocr",                  "read"),
            ("ocr.inference",                   "ocr",                  "inference"),
            ("speaker-diarization.read",        "speaker-diarization",  "read"),
            ("speaker-diarization.inference",   "speaker-diarization",  "inference"),
            ("transliteration.read",            "transliteration",      "read"),
            ("transliteration.inference",       "transliteration",      "inference"),
            ("pipeline.read",                   "pipeline",             "read"),
            ("pipeline.inference",              "pipeline",             "inference"),
            ("llm.read",                        "llm",                  "read"),
            ("llm.inference",                   "llm",                  "inference"),
            ("model-management.read",           "model-management",     "read"),
            ("model-management.inference",      "model-management",     "inference"),
            # Observability
            ("logs.read",   "logs",   "read"),
            ("traces.read", "traces", "read"),
            # Tenant management (consolidated into auth-service)
            ("tenant.create",       "tenant",       "create"),
            ("tenant.read",         "tenant",       "read"),
            ("tenant.update",       "tenant",       "update"),
            ("tenant.users.read",   "tenant.users", "read"),
            ("tenant.users.update", "tenant.users", "update"),
            # PII Guard
            ("pii_guard.inference", "pii_guard", "inference"),
            ("pii_guard.admin",     "pii_guard", "admin"),
        ]
        permission_names = [p[0] for p in permissions]
        permission_names_quoted = "', '".join(permission_names)

        # Remove permissions (and their role_permission rows) not in seed list
        adapter.execute(
            f"""
            DELETE FROM role_permission
            WHERE permission_id NOT IN (
                SELECT permission_id FROM permissions WHERE name IN ('{permission_names_quoted}')
            )
            """
        )
        adapter.execute(
            f"""
            DELETE FROM permissions
            WHERE name NOT IN ('{permission_names_quoted}')
            """
        )

        for name, resource, action in permissions:
            adapter.execute(
                """
                INSERT INTO permissions (name, resource, action, created_by)
                VALUES (:name, :resource, :action, :created_by)
                ON CONFLICT (name) DO UPDATE
                  SET resource = EXCLUDED.resource,
                      action   = EXCLUDED.action
                """,
                {"name": name, "resource": resource, "action": action, "created_by": SEEDER_ID},
            )
        print(f"    ✓ Seeded {len(permissions)} permissions in ai4iplatform_auth")

        # ── 3. Role-Permissions (clean slate for seeded roles) ─────────────────
        # No unique constraint on role_permission(role_id, permission_id) so we
        # delete all existing mappings for our roles then re-insert.
        adapter.execute(
            f"""
            DELETE FROM role_permission
            WHERE role_id IN (
                SELECT role_id FROM roles WHERE name IN ('{role_names_quoted}')
            )
            """
        )

        # ADMIN — full access
        adapter.execute(
            f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.role_id, p.permission_id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.create','users.read','users.update','users.delete',
              'configs.create','configs.read','configs.update','configs.delete',
              'metrics.read','metrics.export',
              'alerts.create','alerts.read','alerts.update','alerts.delete',
              'dashboards.create','dashboards.read','dashboards.update','dashboards.delete',
              'apiKey.create','apiKey.read','apiKey.delete','apiKey.update',
              'service.create','service.delete','service.update','service.read',
              'model.create','model.read','model.update','model.delete',
              'model.publish','model.unpublish',
              'roles.assign','roles.remove','roles.read',
              'pii_guard.admin','pii_guard.inference',
              'tenant.create','tenant.read','tenant.update',
              'tenant.users.read','tenant.users.update'
            )
            WHERE r.name = 'ADMIN'
            """
        )
        print("    ✓ Assigned permissions to ADMIN role")

        # USER
        adapter.execute(
            f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.role_id, p.permission_id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.read','users.update',
              'service.read','apiKey.delete',
              'asr.inference','audio-lang-detection.inference',
              'language-detection.inference','language-diarization.inference',
              'llm.inference','model-management.inference',
              'ner.inference','nmt.inference',
              'ocr.inference','pipeline.inference','pii_guard.inference',
              'speaker-diarization.inference','transliteration.inference','tts.inference'
            )
            WHERE r.name = 'USER'
            """
        )
        print("    ✓ Assigned permissions to USER role")

        # GUEST — read-only + core inference
        adapter.execute(
            f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.role_id, p.permission_id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.read','roles.read','service.read',
              'asr.inference','nmt.inference','tts.inference'
            )
            WHERE r.name = 'GUEST'
            """
        )
        print("    ✓ Assigned permissions to GUEST role")

        # MODERATOR
        adapter.execute(
            f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.role_id, p.permission_id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.create','users.read','users.update','users.delete',
              'configs.create','configs.read','configs.update','configs.delete',
              'metrics.read','metrics.export',
              'alerts.create','alerts.read','alerts.update','alerts.delete',
              'dashboards.create','dashboards.read','dashboards.update','dashboards.delete',
              'apiKey.delete',
              'service.create','service.delete','service.update','service.read',
              'model.create','model.read','model.update','model.delete',
              'model.publish','model.unpublish',
              'asr.inference','audio-lang-detection.inference',
              'language-detection.inference','language-diarization.inference',
              'llm.inference','model-management.inference',
              'ner.inference','nmt.inference',
              'ocr.inference','pipeline.inference','pii_guard.inference',
              'speaker-diarization.inference','transliteration.inference','tts.inference',
              'tenant.read','tenant.users.read','tenant.users.update'
            )
            WHERE r.name = 'MODERATOR'
            """
        )
        print("    ✓ Assigned permissions to MODERATOR role")

        # TENANT ADMIN — tenant-scoped management of their own tenant's users.
        # Cannot create or modify peer tenants (tenant.create / tenant.update bound to ADMIN/MODERATOR only).
        adapter.execute(
            f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.role_id, p.permission_id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.create','users.read','users.update',
              'service.read','model.read',
              'apiKey.create','apiKey.read','apiKey.update','apiKey.delete',
              'roles.assign','roles.read',
              'pii_guard.admin',
              'asr.inference','audio-lang-detection.inference',
              'language-detection.inference','language-diarization.inference',
              'llm.inference','model-management.inference',
              'ner.inference','nmt.inference',
              'ocr.inference','pipeline.inference',
              'speaker-diarization.inference','transliteration.inference','tts.inference',
              'tenant.read','tenant.users.read','tenant.users.update'
            )
            WHERE r.name = 'TENANT ADMIN'
            """
        )
        print("    ✓ Assigned permissions to TENANT ADMIN role")
