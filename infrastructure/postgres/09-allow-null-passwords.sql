-- Migration: Allow NULL passwords for OAuth users
-- This enables users to sign in via OAuth without requiring a password

\c auth_db;

-- Alter users table to allow NULL passwords (for OAuth users)
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

-- Add comment to document the change
COMMENT ON COLUMN users.password_hash IS 'Password hash for traditional login. NULL for OAuth-only users.';


