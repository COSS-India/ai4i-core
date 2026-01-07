-- ============================================================================
-- Model and Service Permissions Mapping to All Roles
-- ============================================================================
-- This script maps all model and service permissions to all roles:
--   - ADMIN (already has all permissions, but included for completeness)
--   - MODERATOR
--   - USER
--   - GUEST
--
-- Permissions being mapped:
--   - service.create, service.delete, service.update, service.read
--   - model.create, model.read, model.update, model.delete
--   - model.publish, model.unpublish
-- ============================================================================

\c auth_db;

-- Map all model and service permissions to ADMIN role
-- (Note: ADMIN already gets all permissions via the general query, but this ensures explicit mapping)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN'
AND p.name IN (
    'service.create', 'service.delete', 'service.update', 'service.read',
    'model.create', 'model.read', 'model.update', 'model.delete',
    'model.publish', 'model.unpublish'
)
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Map all model and service permissions to MODERATOR role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR'
AND p.name IN (
    'service.create', 'service.delete', 'service.update', 'service.read',
    'model.create', 'model.read', 'model.update', 'model.delete',
    'model.publish', 'model.unpublish'
)
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Map all model and service permissions to USER role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER'
AND p.name IN (
    'service.create', 'service.delete', 'service.update', 'service.read',
    'model.create', 'model.read', 'model.update', 'model.delete',
    'model.publish', 'model.unpublish'
)
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Map all model and service permissions to GUEST role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'GUEST'
AND p.name IN (
    'service.create', 'service.delete', 'service.update', 'service.read',
    'model.create', 'model.read', 'model.update', 'model.delete',
    'model.publish', 'model.unpublish'
)
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Verification query (optional - uncomment to verify mappings)
-- SELECT r.name as role_name, p.name as permission_name
-- FROM roles r
-- JOIN role_permissions rp ON r.id = rp.role_id
-- JOIN permissions p ON rp.permission_id = p.id
-- WHERE p.name IN (
--     'service.create', 'service.delete', 'service.update', 'service.read',
--     'model.create', 'model.read', 'model.update', 'model.delete',
--     'model.publish', 'model.unpublish'
-- )
-- ORDER BY r.name, p.name;

