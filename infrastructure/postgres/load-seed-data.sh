#!/bin/bash
# Script to load seed data into PostgreSQL
# This populates roles, permissions, and assigns roles to users

set -e

echo "Loading seed data into PostgreSQL..."

# Load seed data
sudo docker exec -i ai4v-postgres psql -U dhruva_user -d auth_db <<EOF
-- Insert default roles
INSERT INTO roles (name, description) VALUES
('ADMIN', 'Administrator with full system access'),
('USER', 'Regular user with standard permissions'),
('GUEST', 'Guest user with read-only access'),
('MODERATOR', 'Moderator with elevated permissions')
ON CONFLICT (name) DO NOTHING;

-- Insert default permissions
INSERT INTO permissions (name, resource, action) VALUES
-- User management permissions
('users.create', 'users', 'create'),
('users.read', 'users', 'read'),
('users.update', 'users', 'update'),
('users.delete', 'users', 'delete'),
-- Configuration permissions
('configs.create', 'configurations', 'create'),
('configs.read', 'configurations', 'read'),
('configs.update', 'configurations', 'update'),
('configs.delete', 'configurations', 'delete'),
-- Metrics permissions
('metrics.read', 'metrics', 'read'),
('metrics.export', 'metrics', 'export'),
-- Alerts permissions
('alerts.create', 'alerts', 'create'),
('alerts.read', 'alerts', 'read'),
('alerts.update', 'alerts', 'update'),
('alerts.delete', 'alerts', 'delete'),
-- Dashboard permissions
('dashboards.create', 'dashboards', 'create'),
('dashboards.read', 'dashboards', 'read'),
('dashboards.update', 'dashboards', 'update'),
('dashboards.delete', 'dashboards', 'delete'),
-- AI service permissions
('asr.inference', 'asr', 'inference'),
('asr.read', 'asr', 'read'),
('tts.inference', 'tts', 'inference'),
('tts.read', 'tts', 'read'),
('nmt.inference', 'nmt', 'inference'),
('nmt.read', 'nmt', 'read')
ON CONFLICT (name) DO NOTHING;

-- Assign permissions to roles
-- ADMIN gets all permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- USER gets read/update on own resources and read on others + AI services
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name IN ('users.read', 'users.update', 'configs.read', 'metrics.read', 'alerts.read', 'dashboards.create', 'dashboards.read', 'dashboards.update', 'asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- GUEST gets read-only access
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'GUEST' 
AND p.name IN ('users.read', 'configs.read', 'metrics.read', 'alerts.read', 'dashboards.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- MODERATOR gets read/update on most resources + AI services
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name IN ('users.read', 'users.update', 'configs.read', 'configs.update', 'metrics.read', 'alerts.read', 'alerts.update', 'dashboards.create', 'dashboards.read', 'dashboards.update', 'asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign ADMIN role to admin user if exists
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.email = 'admin@dhruva-platform.com' AND r.name = 'ADMIN'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Assign USER role to existing users who don't have any role
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE r.name = 'USER'
AND u.id NOT IN (SELECT user_id FROM user_roles)
ON CONFLICT (user_id, role_id) DO NOTHING;

SELECT 'Seed data loaded successfully!' as status;
EOF

echo "Seed data loading complete!"
echo ""
echo "Roles and permissions have been created."
echo "Existing users without roles have been assigned USER role."

