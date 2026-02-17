-- Migration: Add rbac_role column to notification_receivers table
-- This allows receivers to be configured with RBAC roles instead of individual email addresses
-- Connect to alerting_db

\c alerting_db;

-- Add rbac_role column (nullable, for backward compatibility)
ALTER TABLE notification_receivers 
ADD COLUMN IF NOT EXISTS rbac_role VARCHAR(50);

-- Add comment
COMMENT ON COLUMN notification_receivers.rbac_role IS 'RBAC role name (ADMIN, MODERATOR, USER, GUEST) - if set, email_to will be resolved from users with this role';

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_notification_receivers_rbac_role ON notification_receivers(rbac_role);

-- Add comment to table
COMMENT ON TABLE notification_receivers IS 'Stores notification channel configurations (email) per organization. Supports both direct email addresses and RBAC role-based email resolution.';

