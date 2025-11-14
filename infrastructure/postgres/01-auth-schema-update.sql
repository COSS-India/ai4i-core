-- Update auth schema to match SQLAlchemy model
-- Run this to update the existing database schema

\c auth_db;

-- Rename password_hash to hashed_password
ALTER TABLE users RENAME COLUMN password_hash TO hashed_password;

-- Add missing columns to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'UTC';
ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en';

-- Update sessions table to match UserSession model
-- First, check if user_sessions table exists, if not create it
CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    refresh_token VARCHAR(255) UNIQUE,
    device_info JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for user_sessions
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_session_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_token ON user_sessions(refresh_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_is_active ON user_sessions(is_active);

-- Update api_keys table to match APIKey model
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_name VARCHAR(100);
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS permissions JSONB DEFAULT '[]'::jsonb;
ALTER TABLE api_keys RENAME COLUMN name TO key_name_old;
ALTER TABLE api_keys DROP COLUMN IF EXISTS key_name_old;

-- Update api_keys to use correct column names
DO $$
BEGIN
    -- If key_name doesn't exist but name does, rename it
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='api_keys' AND column_name='name' AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='api_keys' AND column_name='key_name')) THEN
        ALTER TABLE api_keys RENAME COLUMN name TO key_name;
    END IF;
    
    -- If last_used_at exists but last_used doesn't, rename it
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='api_keys' AND column_name='last_used_at' AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='api_keys' AND column_name='last_used')) THEN
        ALTER TABLE api_keys RENAME COLUMN last_used_at TO last_used;
    END IF;
END $$;

-- Ensure api_keys has permissions column with default
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='api_keys' AND column_name='permissions') THEN
        ALTER TABLE api_keys ADD COLUMN permissions JSONB DEFAULT '[]'::jsonb;
    END IF;
END $$;


