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
        
        # Insert default permissions
        permissions = [
            # User management
            ('users.create', 'users', 'create'),
            ('users.read', 'users', 'read'),
            ('users.update', 'users', 'update'),
            ('users.delete', 'users', 'delete'),
            # Configuration
            ('configs.create', 'configurations', 'create'),
            ('configs.read', 'configurations', 'read'),
            ('configs.update', 'configurations', 'update'),
            ('configs.delete', 'configurations', 'delete'),
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
            # AI Services
            ('asr.inference', 'asr', 'inference'),
            ('asr.read', 'asr', 'read'),
            ('tts.inference', 'tts', 'inference'),
            ('tts.read', 'tts', 'read'),
            ('nmt.inference', 'nmt', 'inference'),
            ('nmt.read', 'nmt', 'read'),
            ('llm.inference', 'llm', 'inference'),
            ('llm.read', 'llm', 'read'),
            ('ocr.inference', 'ocr', 'inference'),
            ('ocr.read', 'ocr', 'read'),
            ('ner.inference', 'ner', 'inference'),
            ('ner.read', 'ner', 'read'),
            ('language_detection.inference', 'language_detection', 'inference'),
            ('language_detection.read', 'language_detection', 'read'),
            ('transliteration.inference', 'transliteration', 'inference'),
            ('transliteration.read', 'transliteration', 'read'),
            ('speaker_diarization.inference', 'speaker_diarization', 'inference'),
            ('speaker_diarization.read', 'speaker_diarization', 'read'),
            ('audio_lang_detection.inference', 'audio_lang_detection', 'inference'),
            ('audio_lang_detection.read', 'audio_lang_detection', 'read'),
            # Observability
            ('logs.read', 'logs', 'read'),
            ('traces.read', 'traces', 'read'),
            # Model Management
            ('model.create', 'model', 'create'),
            ('model.read', 'model', 'read'),
            ('model.update', 'model', 'update'),
            ('model.delete', 'model', 'delete'),
            ('model.publish', 'model', 'publish'),
            ('model.unpublish', 'model', 'unpublish'),
            # Service Management
            ('service.create', 'service', 'create'),
            ('service.read', 'service', 'read'),
            ('service.update', 'service', 'update'),
            ('service.delete', 'service', 'delete'),
        ]
        
        for name, resource, action in permissions:
            adapter.execute(
                """
                INSERT INTO permissions (name, resource, action)
                VALUES (:name, :resource, :action)
                ON CONFLICT (name) DO NOTHING
                """,
                {'name': name, 'resource': resource, 'action': action}
            )
        print(f"    ✓ Seeded {len(permissions)} permissions")
        
        # Assign all permissions to ADMIN role
        adapter.execute("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.name = 'ADMIN'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        """)
        print("    ✓ Assigned all permissions to ADMIN role")
        
        # Assign read permissions and AI inference permissions to USER role
        adapter.execute("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.name = 'USER' 
            AND p.name IN (
                'users.read', 'users.update', 'configs.read', 'metrics.read', 
                'alerts.read', 'dashboards.create', 'dashboards.read', 'dashboards.update',
                'model.read', 'service.read',
                'asr.inference', 'asr.read', 'tts.inference', 'tts.read', 
                'nmt.inference', 'nmt.read', 'llm.inference', 'llm.read',
                'ocr.inference', 'ocr.read', 'ner.inference', 'ner.read',
                'language_detection.inference', 'language_detection.read',
                'transliteration.inference', 'transliteration.read',
                'speaker_diarization.inference', 'speaker_diarization.read',
                'audio_lang_detection.inference', 'audio_lang_detection.read',
                'logs.read', 'traces.read'
            )
            ON CONFLICT (role_id, permission_id) DO NOTHING
        """)
        print("    ✓ Assigned permissions to USER role")
        
        # Assign read-only permissions to GUEST role
        adapter.execute("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.name = 'GUEST' 
            AND p.name IN (
                'users.read', 'configs.read', 'metrics.read', 'alerts.read', 
                'dashboards.read', 'model.read', 'service.read',
                'logs.read', 'traces.read'
            )
            ON CONFLICT (role_id, permission_id) DO NOTHING
        """)
        print("    ✓ Assigned permissions to GUEST role")
        
        # Assign permissions to MODERATOR role
        adapter.execute("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.name = 'MODERATOR' 
            AND p.name LIKE '%.read' 
               OR p.name LIKE '%.update' 
               OR p.name LIKE 'model.%' 
               OR p.name LIKE 'service.%'
               OR p.name LIKE '%.inference'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        """)
        print("    ✓ Assigned permissions to MODERATOR role")
