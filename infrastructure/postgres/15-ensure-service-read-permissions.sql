-- ============================================================================
-- Ensure Service Read Permissions for NMT, ASR, TTS Services
-- ============================================================================
-- This script ensures that users have 'service.read' permission to access
-- model-management services endpoint for filtering by task_type (nmt, asr, tts).
--
-- The endpoint /api/v1/model-management/services/?task_type=nmt requires
-- 'service.read' permission which should be assigned to USER role.
-- ============================================================================

\c auth_db;

-- Ensure 'service.read' permission exists
INSERT INTO permissions (name, resource, action) VALUES
('service.read', 'services', 'read')
ON CONFLICT (name) DO NOTHING;

-- Ensure USER role has service.read permission
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name = 'service.read'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Ensure MODERATOR role has service.read permission
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name = 'service.read'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Ensure GUEST role has service.read permission (for read-only access)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'GUEST' 
AND p.name = 'service.read'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- ADMIN role already has all permissions, but ensure it's explicitly set
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN' 
AND p.name = 'service.read'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Verification query: Check which roles have service.read permission
-- Uncomment to verify:
-- SELECT r.name as role_name, p.name as permission_name
-- FROM roles r
-- JOIN role_permissions rp ON r.id = rp.role_id
-- JOIN permissions p ON rp.permission_id = p.id
-- WHERE p.name = 'service.read'
-- ORDER BY r.name;
