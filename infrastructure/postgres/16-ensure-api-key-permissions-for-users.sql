-- ============================================================================
-- Ensure API Key Permissions for USER Role
-- ============================================================================
-- This script ensures that users have API key management permissions to:
-- - Create their own API keys (apiKey.create)
-- - Read their own API keys (apiKey.read)
-- - Update/select their own API keys (apiKey.update)
-- - Delete their own API keys (apiKey.delete)
--
-- The endpoint /api/v1/auth/api-keys/select requires 'apiKey.update' permission.
-- Note: The endpoints already enforce that users can only manage their own keys.
-- ============================================================================

\c auth_db;

-- Ensure API key permissions exist
INSERT INTO permissions (name, resource, action) VALUES
('apiKey.create', 'apiKey', 'create'),
('apiKey.read', 'apiKey', 'read'),
('apiKey.update', 'apiKey', 'update'),
('apiKey.delete', 'apiKey', 'delete')
ON CONFLICT (name) DO NOTHING;

-- Ensure USER role has all API key management permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name IN ('apiKey.create', 'apiKey.read', 'apiKey.update', 'apiKey.delete')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Ensure MODERATOR role has all API key management permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name IN ('apiKey.create', 'apiKey.read', 'apiKey.update', 'apiKey.delete')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- GUEST role should not have API key management permissions (read-only access)
-- ADMIN role already has all permissions, but ensure it's explicitly set
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN' 
AND p.name IN ('apiKey.create', 'apiKey.read', 'apiKey.update', 'apiKey.delete')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Verification query: Check which roles have API key permissions
-- Uncomment to verify:
-- SELECT r.name as role_name, p.name as permission_name
-- FROM roles r
-- JOIN role_permissions rp ON r.id = rp.role_id
-- JOIN permissions p ON rp.permission_id = p.id
-- WHERE p.resource = 'apiKey'
-- ORDER BY r.name, p.name;
