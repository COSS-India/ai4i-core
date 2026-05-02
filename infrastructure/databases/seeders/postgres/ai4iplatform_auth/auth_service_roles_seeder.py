"""
Auth Service Roles, Permissions, and Role-Permissions Seeder (ai4iplatform_auth)

Reseed semantics: idempotent, preserves user_role.
  - permissions table is rewritten with explicit IDs (so api_permissions.json
    can hard-code permission_id integers).
  - role_permission table is wiped and recreated.
  - roles are UPSERTed by name (no DELETE), so existing user_role.role_id
    rows continue to point to the right role.

ID convention (stable across services — api_permissions.json embeds these IDs):
    1       'admin' sentinel — granted only to ADMIN role
    2-10    reserved for future system-level permissions
    11+     feature permissions, grouped in 10-wide buckets per resource family

Roles (ADMIN, USER, GUEST, MODERATOR, TENANT ADMIN). ADMIN gets every
permission via CROSS JOIN; the other roles get explicit lists.
"""
from infrastructure.databases.core.base_seeder import BaseSeeder

# Fixed identity for all rows written by seeders — readable as "seed0000…"
SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


class AuthServiceRolesSeeder(BaseSeeder):
    """Seed default roles, permissions, and role-permissions for ai4iplatform_auth."""

    database = "ai4iplatform_auth"

    def run(self, adapter):
        roles = [
            ("ADMIN",        "Administrator with full system access"),
            ("USER",         "Regular user with standard permissions"),
            ("GUEST",        "Guest: own profile read + ASR/NMT/TTS inference"),
            ("MODERATOR",    "Moderator with elevated management permissions"),
            ("TENANT ADMIN", "Tenant administrator with tenant-scoped management permissions"),
        ]

        # (id, name, resource, action)
        permissions = [
            # System sentinel
            (1,   "admin",                          "admin",              "admin"),

            # Users (11-19)
            (11,  "users.create",                   "users",              "create"),
            (12,  "users.read",                     "users",              "read"),
            (13,  "users.update",                   "users",              "update"),
            (14,  "users.delete",                   "users",              "delete"),
            (15,  "users.profile.read",             "users.profile",      "read"),
            (16,  "users.profile.update",           "users.profile",      "update"),
            (17,  "users.password.change",          "users.password",     "change"),

            # Roles & permissions (20-29)
            (20,  "roles.read",                     "roles",              "read"),
            (21,  "roles.assign",                   "roles",              "assign"),
            (22,  "roles.remove",                   "roles",              "remove"),
            (23,  "permissions.read",               "permissions",        "read"),

            # API keys (30-39)
            (30,  "apiKey.create",                  "apiKey",             "create"),
            (31,  "apiKey.read",                    "apiKey",             "read"),
            (32,  "apiKey.update",                  "apiKey",             "update"),
            (33,  "apiKey.delete",                  "apiKey",             "delete"),
            (34,  "apiKey.read.all",                "apiKey",             "read.all"),

            # Tenants (40-49)
            (40,  "tenant.create",                  "tenant",             "create"),
            (41,  "tenant.read",                    "tenant",             "read"),
            (42,  "tenant.update",                  "tenant",             "update"),
            (44,  "tenant.users.read",              "tenant.users",       "read"),
            (45,  "tenant.users.create",            "tenant.users",       "create"),
            (46,  "tenant.users.update",            "tenant.users",       "update"),
            (47,  "tenant.users.delete",            "tenant.users",       "delete"),

            # Services & models (50-59)
            (50,  "service.create",                 "service",            "create"),
            (51,  "service.read",                   "service",            "read"),
            (52,  "service.update",                 "service",            "update"),
            (53,  "service.delete",                 "service",            "delete"),
            (54,  "model.create",                   "model",              "create"),
            (55,  "model.read",                     "model",              "read"),
            (56,  "model.update",                   "model",              "update"),
            (57,  "model.delete",                   "model",              "delete"),

            # Inference (60-71) — one per service
            (60,  "nmt.inference",                  "nmt",                  "inference"),
            (61,  "asr.inference",                  "asr",                  "inference"),
            (62,  "tts.inference",                  "tts",                  "inference"),
            (63,  "llm.inference",                  "llm",                  "inference"),
            (64,  "ner.inference",                  "ner",                  "inference"),
            (65,  "ocr.inference",                  "ocr",                  "inference"),
            (66,  "transliteration.inference",      "transliteration",      "inference"),
            (67,  "language-detection.inference",   "language-detection",   "inference"),
            (68,  "language-diarization.inference", "language-diarization", "inference"),
            (69,  "speaker-diarization.inference",  "speaker-diarization",  "inference"),
            (70,  "audio-lang-detection.inference", "audio-lang-detection", "inference"),
            (71,  "pipeline.inference",             "pipeline",             "inference"),

            # Inference list/metadata (80-85) — voices/models/languages endpoints
            (80,  "nmt.read",                       "nmt",                  "read"),
            (81,  "asr.read",                       "asr",                  "read"),
            (82,  "tts.read",                       "tts",                  "read"),
            (83,  "llm.read",                       "llm",                  "read"),
            (84,  "transliteration.read",           "transliteration",      "read"),
            (85,  "language-detection.read",        "language-detection",   "read"),

            # PII Guard (90-99)
            (90,  "pii_guard.inference",            "pii_guard",            "inference"),
            (91,  "pii_guard.admin",                "pii_guard",            "admin"),
            (92,  "pii_guard.audit.read",           "pii_guard.audit",      "read"),

            # Policies / PII types / audit (100-109)
            (100, "policies.read",                  "policies",             "read"),
            (101, "policies.create",                "policies",             "create"),
            (102, "policies.update",                "policies",             "update"),
            (103, "policies.delete",                "policies",             "delete"),
            (104, "policies.assign",                "policies",             "assign"),
            (105, "pii_types.read",                 "pii_types",            "read"),
            (106, "pii_types.create",               "pii_types",            "create"),
            (107, "pii_types.update",               "pii_types",            "update"),
            (108, "pii_types.delete",               "pii_types",            "delete"),
            (109, "audit_logs.read",                "audit_logs",           "read"),

            # Dashboards / alerts / metrics (110-119)
            (110, "metrics.read",                   "metrics",              "read"),
            (111, "metrics.export",                 "metrics",              "export"),
            (112, "dashboards.read",                "dashboards",           "read"),
            (113, "dashboards.create",              "dashboards",           "create"),
            (114, "dashboards.update",              "dashboards",           "update"),
            (115, "dashboards.delete",              "dashboards",           "delete"),
            (116, "alerts.read",                    "alerts",               "read"),
            (117, "alerts.create",                  "alerts",               "create"),
            (118, "alerts.update",                  "alerts",               "update"),
            (119, "alerts.delete",                  "alerts",               "delete"),

            # Configs (120-129)
            (120, "configs.read",                   "configs",              "read"),
            (121, "configs.create",                 "configs",              "create"),
            (122, "configs.update",                 "configs",              "update"),
            (123, "configs.delete",                 "configs",              "delete"),

            # Telemetry / logs / traces (130-139)
            (130, "logs.read",                      "logs",                 "read"),
            (131, "traces.read",                    "traces",               "read"),
            (132, "telemetry.write",                "telemetry",            "write"),
        ]

        # 1) Wipe role_permission (depends on both roles and permissions). Then wipe
        # permissions — safe now because nothing else FK-references it. We do NOT
        # truncate roles, so user_role.role_id stays valid.
        adapter.execute("DELETE FROM role_permission;")
        adapter.execute("DELETE FROM permissions;")

        # 2) Upsert roles by name (preserves roles.id, updates description in place).
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
        print(f"    ✓ Upserted {len(roles)} roles")

        # 3) Insert permissions with explicit IDs, then bump sequence past max id.
        for pid, name, resource, action in permissions:
            adapter.execute(
                """
                INSERT INTO permissions (id, name, resource, action, created_by)
                VALUES (:id, :name, :resource, :action, :created_by)
                """,
                {
                    "id": pid,
                    "name": name,
                    "resource": resource,
                    "action": action,
                    "created_by": SEEDER_ID,
                },
            )
        max_id = max(p[0] for p in permissions)
        adapter.execute(
            f"SELECT setval(pg_get_serial_sequence('permissions', 'id'), {max_id});"
        )
        print(f"    ✓ Seeded {len(permissions)} permissions (max id = {max_id})")

        # 4) Role grants.

        # ADMIN: every permission (including the `admin` sentinel id=1).
        adapter.execute(
            f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r CROSS JOIN permissions p
            WHERE r.name = 'ADMIN'
            """
        )
        print("    ✓ ADMIN: granted all permissions")

        # USER: own-profile management + inference access.
        adapter.execute(
            f"""
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
            """
        )
        print("    ✓ USER: granted profile + inference permissions")

        # GUEST: minimal — own profile read + ASR/NMT/TTS inference only.
        adapter.execute(
            f"""
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
            """
        )
        print("    ✓ GUEST: granted minimal inference permissions")

        # MODERATOR: full management except tenant-level ops and policy admin.
        adapter.execute(
            f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.create',
              'users.read',
              'users.update',
              'users.delete',
              'users.profile.read',
              'users.profile.update',
              'users.password.change',
              'roles.read',
              'permissions.read',
              'apiKey.create',
              'apiKey.read',
              'apiKey.update',
              'apiKey.delete',
              'service.create',
              'service.read',
              'service.update',
              'service.delete',
              'model.create',
              'model.read',
              'model.update',
              'model.delete',
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
              'tts.inference',
              'configs.read',
              'configs.create',
              'configs.update',
              'configs.delete',
              'metrics.read',
              'metrics.export',
              'alerts.read',
              'alerts.create',
              'alerts.update',
              'alerts.delete',
              'dashboards.read',
              'dashboards.create',
              'dashboards.update',
              'dashboards.delete',
              'tenant.read',
              'tenant.users.read',
              'tenant.users.update'
            )
            WHERE r.name = 'MODERATOR'
            """
        )
        print("    ✓ MODERATOR: granted management permissions")

        # TENANT ADMIN: tenant-scoped management + inference.
        adapter.execute(
            f"""
            INSERT INTO role_permission (role_id, permission_id, created_by)
            SELECT r.id, p.id, '{SEEDER_ID}'
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.create',
              'users.read',
              'users.update',
              'users.profile.read',
              'users.profile.update',
              'users.password.change',
              'roles.read',
              'roles.assign',
              'apiKey.create',
              'apiKey.read',
              'apiKey.update',
              'apiKey.delete',
              'service.read',
              'model.read',
              'pii_guard.admin',
              'asr.inference',
              'audio-lang-detection.inference',
              'language-detection.inference',
              'language-diarization.inference',
              'llm.inference',
              'ner.inference',
              'nmt.inference',
              'ocr.inference',
              'pipeline.inference',
              'speaker-diarization.inference',
              'transliteration.inference',
              'tts.inference',
              'tenant.read',
              'tenant.users.read',
              'tenant.users.create',
              'tenant.users.update',
              'tenant.users.delete'
            )
            WHERE r.name = 'TENANT ADMIN'
            """
        )
        print("    ✓ TENANT ADMIN: granted tenant-scoped management + inference")
