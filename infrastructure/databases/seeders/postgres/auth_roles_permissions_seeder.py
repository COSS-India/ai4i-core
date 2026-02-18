"""
Auth Roles and Permissions Seeder
Seeds default roles and permissions for the auth system
"""
from infrastructure.databases.core.base_seeder import BaseSeeder


class AuthRolesPermissionsSeeder(BaseSeeder):
    """Seed default roles and permissions for auth_db"""
    
    database = 'auth_db'  # Target database
    
    def run(self, adapter):
        """Run seeder"""
        # Insert default roles
        roles = [
            ('ADMIN', 'Administrator with full system access'),
            ('USER', 'Regular user with standard permissions'),
            ('GUEST', 'Guest user with read-only access'),
            ('MODERATOR', 'Moderator with elevated permissions')
        ]
        
        for name, description in roles:
            adapter.execute(
                """
                INSERT INTO roles (name, description)
                VALUES (:name, :description)
                ON CONFLICT (name) DO NOTHING
                """,
                {'name': name, 'description': description}
            )
        print(f"    ✓ Seeded {len(roles)} roles")
        
        # Insert default permissions - mirror infrastructure/postgres/load-seed-data.sh
        permissions = [
            # User management
            ('users.create', 'users', 'create'),
            ('users.read', 'users', 'read'),
            ('users.update', 'users', 'update'),
            ('users.delete', 'users', 'delete'),

            # Configuration
            ('configs.create', 'configs', 'create'),
            ('configs.read', 'configs', 'read'),
            ('configs.update', 'configs', 'update'),
            ('configs.delete', 'configs', 'delete'),

            # Metrics
            ('metrics.read', 'metrics', 'read'),
            ('metrics.export', 'metrics', 'export'),

            # Alerts
            ('alerts.create', 'alerts', 'create'),
            ('alerts.read', 'alerts', 'read'),
            ('alerts.update', 'alerts', 'update'),
            ('alerts.delete', 'alerts', 'delete'),

            # Dashboards
            ('dashboards.create', 'dashboards', 'create'),
            ('dashboards.read', 'dashboards', 'read'),
            ('dashboards.update', 'dashboards', 'update'),
            ('dashboards.delete', 'dashboards', 'delete'),

            # API Key Management
            ('apiKey.create', 'apiKey', 'create'),
            ('apiKey.read', 'apiKey', 'read'),
            ('apiKey.delete', 'apiKey', 'delete'),
            ('apiKey.update', 'apiKey', 'update'),

            # Service Management
            ('service.create', 'service', 'create'),
            ('service.delete', 'service', 'delete'),
            ('service.update', 'service', 'update'),
            ('service.read', 'service', 'read'),

            # Model Management
            ('model.create', 'model', 'create'),
            ('model.read', 'model', 'read'),
            ('model.update', 'model', 'update'),
            ('model.delete', 'model', 'delete'),
            ('model.publish', 'model', 'publish'),
            ('model.unpublish', 'model', 'unpublish'),

            # Role Management
            ('roles.assign', 'roles', 'assign'),
            ('roles.remove', 'roles', 'remove'),
            ('roles.read', 'roles', 'read'),

            # AI Services (task permissions)
            ('asr.inference', 'asr', 'inference'),
            ('asr.read', 'asr', 'read'),
            ('tts.inference', 'tts', 'inference'),
            ('tts.read', 'tts', 'read'),
            ('nmt.inference', 'nmt', 'inference'),
            ('nmt.read', 'nmt', 'read'),

            ('audio-lang.read', 'audio-lang', 'read'),
            ('audio-lang.inference', 'audio-lang', 'inference'),

            ('language-detection.read', 'language-detection', 'read'),
            ('language-detection.inference', 'language-detection', 'inference'),

            ('language-diarization.read', 'language-diarization', 'read'),
            ('language-diarization.inference', 'language-diarization', 'inference'),

            ('ner.inference', 'ner', 'inference'),

            ('ocr.read', 'ocr', 'read'),
            ('ocr.inference', 'ocr', 'inference'),

            ('speaker-diarization.read', 'speaker-diarization', 'read'),
            ('speaker-diarization.inference', 'speaker-diarization', 'inference'),

            ('transliteration.read', 'transliteration', 'read'),
            ('transliteration.inference', 'transliteration', 'inference'),

            ('pipeline.read', 'pipeline', 'read'),
            ('pipeline.inference', 'pipeline', 'inference'),

            ('llm.read', 'llm', 'read'),
            ('llm.inference', 'llm', 'inference'),

            # Observability
            ('logs.read', 'logs', 'read'),
            ('traces.read', 'traces', 'read'),
        ]
        
        for name, resource, action in permissions:
            adapter.execute(
                """
                INSERT INTO permissions (name, resource, action)
                VALUES (:name, :resource, :action)
                ON CONFLICT (name) DO UPDATE
                  SET resource = EXCLUDED.resource,
                      action   = EXCLUDED.action
                """,
                {'name': name, 'resource': resource, 'action': action}
            )
        print(f"    ✓ Seeded {len(permissions)} permissions")
        
        # ------------------------------------------------------------------
        # ROLE_PERMISSIONS: mirror the logic from load-seed-data.sh
        # ------------------------------------------------------------------

        # ADMIN: explicit list of permissions
        adapter.execute(
            """
            DELETE FROM role_permissions
            WHERE role_id IN (SELECT id FROM roles WHERE name = 'ADMIN');
            """
        )
        adapter.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.create',
              'users.read',
              'users.update',
              'users.delete',
              'configs.create',
              'configs.read',
              'configs.update',
              'configs.delete',
              'metrics.read',
              'metrics.export',
              'alerts.create',
              'alerts.read',
              'alerts.update',
              'alerts.delete',
              'dashboards.create',
              'dashboards.read',
              'dashboards.update',
              'dashboards.delete',
              'apiKey.create',
              'apiKey.read',
              'apiKey.delete',
              'apiKey.update',
              'service.create',
              'service.delete',
              'service.update',
              'service.read',
              'model.create',
              'model.read',
              'model.update',
              'model.delete',
              'model.publish',
              'model.unpublish',
              'roles.assign',
              'roles.remove',
              'roles.read'
            )
            WHERE r.name = 'ADMIN'
            ON CONFLICT (role_id, permission_id) DO NOTHING;
            """
        )
        print("    ✓ Assigned permissions to ADMIN role (from seed script)")

        # USER: same as load-seed-data.sh (users.read, users.update)
        adapter.execute(
            """
            DELETE FROM role_permissions
            WHERE role_id IN (SELECT id FROM roles WHERE name = 'USER');
            """
        )
        adapter.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.read',
              'users.update'
            )
            WHERE r.name = 'USER'
            ON CONFLICT (role_id, permission_id) DO NOTHING;
            """
        )
        print("    ✓ Assigned permissions to USER role (from seed script)")

        # GUEST: same as load-seed-data.sh (users.read, users.update)
        adapter.execute(
            """
            DELETE FROM role_permissions
            WHERE role_id IN (SELECT id FROM roles WHERE name = 'GUEST');
            """
        )
        adapter.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.read',
              'users.update'
            )
            WHERE r.name = 'GUEST'
            ON CONFLICT (role_id, permission_id) DO NOTHING;
            """
        )
        print("    ✓ Assigned permissions to GUEST role (from seed script)")

        # MODERATOR: explicit list from load-seed-data.sh
        adapter.execute(
            """
            DELETE FROM role_permissions
            WHERE role_id IN (SELECT id FROM roles WHERE name = 'MODERATOR');
            """
        )
        adapter.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            JOIN permissions p ON p.name IN (
              'users.create',
              'users.read',
              'users.update',
              'users.delete',
              'configs.create',
              'configs.read',
              'configs.update',
              'configs.delete',
              'metrics.read',
              'metrics.export',
              'alerts.create',
              'alerts.read',
              'alerts.update',
              'alerts.delete',
              'dashboards.create',
              'dashboards.read',
              'dashboards.update',
              'dashboards.delete',
              'service.create',
              'service.delete',
              'service.update',
              'service.read',
              'model.create',
              'model.read',
              'model.update',
              'model.delete',
              'model.publish',
              'model.unpublish'
            )
            WHERE r.name = 'MODERATOR'
            ON CONFLICT (role_id, permission_id) DO NOTHING;
            """
        )
        print("    ✓ Assigned permissions to MODERATOR role (from seed script)")
