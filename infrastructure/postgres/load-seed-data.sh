#!/bin/bash
# Script to load seed data into PostgreSQL
# This populates roles, permissions, and assigns roles to users

set -e

echo "Loading seed data into PostgreSQL (auth_db: roles, permissions, role_permissions)..."

# Load seed data directly into the running Postgres (auth_db)
sudo docker exec -i ai4v-postgres psql -U dhruva_user -d auth_db <<'EOF'
-- NOTE:
-- This seed script reflects the **current** state of auth_db for:
--   - roles
--   - permissions
--   - role_permissions
--
-- It is written to be idempotent and to match the live data that was
-- observed in the running database.

BEGIN;

----------------------------------------------------------------------
-- ROLES (by name, letting DB assign IDs)
----------------------------------------------------------------------
INSERT INTO roles (name, description) VALUES
  ('ADMIN', 'Administrator with full system access'),
  ('USER', 'Regular user with standard permissions'),
  ('GUEST', 'Guest user with read-only access'),
  ('MODERATOR', 'Moderator with elevated permissions')
ON CONFLICT (name) DO UPDATE
  SET description = EXCLUDED.description;

----------------------------------------------------------------------
-- PERMISSIONS (by name, letting DB assign IDs)
----------------------------------------------------------------------
INSERT INTO permissions (name, resource, action) VALUES
  ('users.create', 'users', 'create'),
  ('users.read',   'users', 'read'),
  ('users.update', 'users', 'update'),
  ('users.delete', 'users', 'delete'),

  ('configs.create', 'configs', 'create'),
  ('configs.read',   'configs', 'read'),
  ('configs.update', 'configs', 'update'),
  ('configs.delete', 'configs', 'delete'),

  ('metrics.read',   'metrics', 'read'),
  ('metrics.export', 'metrics', 'export'),

  ('alerts.create', 'alerts', 'create'),
  ('alerts.read',   'alerts', 'read'),
  ('alerts.update', 'alerts', 'update'),
  ('alerts.delete', 'alerts', 'delete'),

  ('dashboards.create', 'dashboards', 'create'),
  ('dashboards.read',   'dashboards', 'read'),
  ('dashboards.update', 'dashboards', 'update'),
  ('dashboards.delete', 'dashboards', 'delete'),

  ('apiKey.create', 'apiKey', 'create'),
  ('apiKey.read',   'apiKey', 'read'),
  ('apiKey.delete', 'apiKey', 'delete'),
  ('apiKey.update', 'apiKey', 'update'),

  ('service.create', 'service', 'create'),
  ('service.delete', 'service', 'delete'),
  ('service.update', 'service', 'update'),
  ('service.read',   'service', 'read'),

  ('model.create',   'model', 'create'),
  ('model.read',     'model', 'read'),
  ('model.update',   'model', 'update'),
  ('model.delete',   'model', 'delete'),
  ('model.publish',  'model', 'publish'),
  ('model.unpublish','model', 'unpublish'),

  ('roles.assign', 'roles', 'assign'),
  ('roles.remove', 'roles', 'remove'),
  ('roles.read',   'roles', 'read'),

  ('asr.inference', 'asr', 'inference'),
  ('asr.read',      'asr', 'read'),
  ('tts.inference', 'tts', 'inference'),
  ('tts.read',      'tts', 'read'),
  ('nmt.inference', 'nmt', 'inference'),
  ('nmt.read',      'nmt', 'read'),

  ('audio-lang.read',      'audio-lang', 'read'),
  ('audio-lang.inference', 'audio-lang', 'inference'),

  ('language-detection.read',      'language-detection', 'read'),
  ('language-detection.inference', 'language-detection', 'inference'),

  ('language-diarization.read',      'language-diarization', 'read'),
  ('language-diarization.inference', 'language-diarization', 'inference'),

  ('ner.inference', 'ner', 'inference'),

  ('ocr.read',      'ocr', 'read'),
  ('ocr.inference', 'ocr', 'inference'),

  ('speaker-diarization.read',      'speaker-diarization', 'read'),
  ('speaker-diarization.inference', 'speaker-diarization', 'inference'),

  ('transliteration.read',      'transliteration', 'read'),
  ('transliteration.inference', 'transliteration', 'inference'),

  ('pipeline.read',      'pipeline', 'read'),
  ('pipeline.inference', 'pipeline', 'inference'),

  ('llm.read',      'llm', 'read'),
  ('llm.inference', 'llm', 'inference')
ON CONFLICT (name) DO UPDATE
  SET resource = EXCLUDED.resource,
      action   = EXCLUDED.action;

----------------------------------------------------------------------
-- ROLE_PERMISSIONS (using role and permission names)
----------------------------------------------------------------------

-- ADMIN: all permissions listed in the live DB
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

-- USER: from current DB (users.read, users.update)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON p.name IN (
  'users.read',
  'users.update'
)
WHERE r.name = 'USER'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- GUEST: from current DB (users.read, users.update)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON p.name IN (
  'users.read',
  'users.update'
)
WHERE r.name = 'GUEST'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- MODERATOR: from current DB
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

COMMIT;

SELECT 'Seed data (roles/permissions/role_permissions) loaded successfully!' AS status;
EOF

echo "Seed data loading complete!"
echo ""
echo "Roles, permissions, and role_permissions have been synced to match the current auth_db state."

