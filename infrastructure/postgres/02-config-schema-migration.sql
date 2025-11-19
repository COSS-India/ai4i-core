-- Migration script to add missing columns to existing tables
-- This script adds columns that were added to the schema after initial table creation
-- Run this script if you have existing tables that need to be updated

\c config_db;

-- Add missing columns to feature_flags table
DO $$
BEGIN
    -- Add unleash_flag_name column
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'feature_flags' 
        AND column_name = 'unleash_flag_name'
    ) THEN
        ALTER TABLE feature_flags ADD COLUMN unleash_flag_name VARCHAR(255);
    END IF;

    -- Add last_synced_at column
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'feature_flags' 
        AND column_name = 'last_synced_at'
    ) THEN
        ALTER TABLE feature_flags ADD COLUMN last_synced_at TIMESTAMP WITH TIME ZONE;
    END IF;

    -- Add evaluation_count column
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'feature_flags' 
        AND column_name = 'evaluation_count'
    ) THEN
        ALTER TABLE feature_flags ADD COLUMN evaluation_count INTEGER DEFAULT 0;
    END IF;

    -- Add last_evaluated_at column
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'feature_flags' 
        AND column_name = 'last_evaluated_at'
    ) THEN
        ALTER TABLE feature_flags ADD COLUMN last_evaluated_at TIMESTAMP WITH TIME ZONE;
    END IF;
END
$$;

