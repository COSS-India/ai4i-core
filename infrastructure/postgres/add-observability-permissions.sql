-- Add Observability Permissions for RBAC
-- This script adds logs.read and traces.read permissions and assigns them to roles
-- Run this script against the auth_db database

\c auth_db;

-- Add permissions if they don't exist
INSERT INTO permissions (resource, action, description) VALUES
('logs', 'read', 'View logs from OpenSearch'),
('traces', 'read', 'View traces from Jaeger')
ON CONFLICT (resource, action) DO NOTHING;

-- Get role IDs
DO $$
DECLARE
    admin_role_id INTEGER;
    moderator_role_id INTEGER;
    user_role_id INTEGER;
    logs_read_permission_id INTEGER;
    traces_read_permission_id INTEGER;
BEGIN
    -- Get role IDs
    SELECT id INTO admin_role_id FROM roles WHERE name = 'ADMIN';
    SELECT id INTO moderator_role_id FROM roles WHERE name = 'MODERATOR';
    SELECT id INTO user_role_id FROM roles WHERE name = 'USER';
    
    -- Get permission IDs
    SELECT id INTO logs_read_permission_id FROM permissions WHERE resource = 'logs' AND action = 'read';
    SELECT id INTO traces_read_permission_id FROM permissions WHERE resource = 'traces' AND action = 'read';
    
    -- Assign logs.read to ADMIN, MODERATOR, and USER
    IF admin_role_id IS NOT NULL AND logs_read_permission_id IS NOT NULL THEN
        INSERT INTO role_permissions (role_id, permission_id)
        VALUES (admin_role_id, logs_read_permission_id)
        ON CONFLICT DO NOTHING;
    END IF;
    
    IF moderator_role_id IS NOT NULL AND logs_read_permission_id IS NOT NULL THEN
        INSERT INTO role_permissions (role_id, permission_id)
        VALUES (moderator_role_id, logs_read_permission_id)
        ON CONFLICT DO NOTHING;
    END IF;
    
    IF user_role_id IS NOT NULL AND logs_read_permission_id IS NOT NULL THEN
        INSERT INTO role_permissions (role_id, permission_id)
        VALUES (user_role_id, logs_read_permission_id)
        ON CONFLICT DO NOTHING;
    END IF;
    
    -- Assign traces.read to ADMIN, MODERATOR, and USER
    IF admin_role_id IS NOT NULL AND traces_read_permission_id IS NOT NULL THEN
        INSERT INTO role_permissions (role_id, permission_id)
        VALUES (admin_role_id, traces_read_permission_id)
        ON CONFLICT DO NOTHING;
    END IF;
    
    IF moderator_role_id IS NOT NULL AND traces_read_permission_id IS NOT NULL THEN
        INSERT INTO role_permissions (role_id, permission_id)
        VALUES (moderator_role_id, traces_read_permission_id)
        ON CONFLICT DO NOTHING;
    END IF;
    
    IF user_role_id IS NOT NULL AND traces_read_permission_id IS NOT NULL THEN
        INSERT INTO role_permissions (role_id, permission_id)
        VALUES (user_role_id, traces_read_permission_id)
        ON CONFLICT DO NOTHING;
    END IF;
    
    RAISE NOTICE 'Observability permissions added successfully';
END $$;

-- Verify permissions were added
SELECT 
    r.name as role_name,
    p.resource,
    p.action,
    p.description
FROM roles r
JOIN role_permissions rp ON r.id = rp.role_id
JOIN permissions p ON rp.permission_id = p.id
WHERE p.resource IN ('logs', 'traces')
ORDER BY r.name, p.resource, p.action;

