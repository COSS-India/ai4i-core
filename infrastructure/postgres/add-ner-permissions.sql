-- ============================================================================
-- Add NER Service Permissions
-- ============================================================================
-- This script adds NER inference and read permissions to the permissions table
-- and assigns them to appropriate roles (ADMIN, USER, GUEST, MODERATOR)
-- ============================================================================

\c auth_db;

-- Insert NER inference permission only (no role assignments)
INSERT INTO permissions (name, resource, action) VALUES
('ner.inference', 'ner', 'inference')
ON CONFLICT (name) DO NOTHING;

-- Verify the permission was added (no role assignments)
SELECT p.name, p.resource, p.action
FROM permissions p
WHERE p.name = 'ner.inference';
