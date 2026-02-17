-- Migration: Add missing columns to users table and update user_sessions columns
-- This script adds is_tenant, selected_api_key_id to users table
-- and changes refresh_token and session_token to TEXT type in user_sessions table
-- Run this script to update existing auth_db schema

\c auth_db;

-- ============================================================================
-- 1. Add is_tenant column to users table
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'users' 
        AND column_name = 'is_tenant'
    ) THEN
        ALTER TABLE users ADD COLUMN is_tenant BOOLEAN DEFAULT NULL;
        RAISE NOTICE 'Added is_tenant column to users table';
    ELSE
        RAISE NOTICE 'Column is_tenant already exists in users table';
    END IF;
END $$;

-- ============================================================================
-- 2. Add selected_api_key_id column to users table
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'users' 
        AND column_name = 'selected_api_key_id'
    ) THEN
        ALTER TABLE users ADD COLUMN selected_api_key_id INTEGER;
        RAISE NOTICE 'Added selected_api_key_id column to users table';
    ELSE
        RAISE NOTICE 'Column selected_api_key_id already exists in users table';
    END IF;
END $$;

-- ============================================================================
-- 3. Add foreign key constraint for selected_api_key_id if it doesn't exist
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.table_constraints 
        WHERE constraint_name = 'users_selected_api_key_id_fkey' 
        AND table_name = 'users'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_selected_api_key_id_fkey
            FOREIGN KEY (selected_api_key_id) REFERENCES api_keys(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added foreign key constraint for selected_api_key_id';
    ELSE
        RAISE NOTICE 'Foreign key constraint users_selected_api_key_id_fkey already exists';
    END IF;
END $$;

-- ============================================================================
-- 4. Alter user_sessions table: change refresh_token and session_token to TEXT
-- ============================================================================
DO $$
BEGIN
    -- Check if user_sessions table exists
    IF EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'user_sessions'
    ) THEN
        -- Check current data type of refresh_token
        IF EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'user_sessions' 
            AND column_name = 'refresh_token'
            AND data_type != 'text'
        ) THEN
            ALTER TABLE user_sessions ALTER COLUMN refresh_token TYPE TEXT;
            RAISE NOTICE 'Changed refresh_token column type to TEXT in user_sessions table';
        ELSE
            RAISE NOTICE 'refresh_token column already has TEXT type or does not exist';
        END IF;
        
        -- Check current data type of session_token
        IF EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'user_sessions' 
            AND column_name = 'session_token'
            AND data_type != 'text'
        ) THEN
            ALTER TABLE user_sessions ALTER COLUMN session_token TYPE TEXT;
            RAISE NOTICE 'Changed session_token column type to TEXT in user_sessions table';
        ELSE
            RAISE NOTICE 'session_token column already has TEXT type or does not exist';
        END IF;
    ELSE
        RAISE NOTICE 'user_sessions table does not exist, skipping column type changes';
    END IF;
END $$;

-- ============================================================================
-- Verification: Show the changes
-- ============================================================================
SELECT 'Migration completed. Verifying changes...' AS status;

-- Verify users table columns
SELECT 
    'users table columns' AS check_type,
    column_name, 
    data_type, 
    is_nullable, 
    column_default
FROM information_schema.columns 
WHERE table_schema = 'public' 
AND table_name = 'users' 
AND column_name IN ('is_tenant', 'selected_api_key_id')
ORDER BY column_name;

-- Verify user_sessions table columns (if table exists)
SELECT 
    'user_sessions table columns' AS check_type,
    column_name, 
    data_type, 
    character_maximum_length,
    is_nullable
FROM information_schema.columns 
WHERE table_schema = 'public' 
AND table_name = 'user_sessions' 
AND column_name IN ('refresh_token', 'session_token')
ORDER BY column_name;
