-- Migration script to fix feature_flags table constraint
-- Run this if you have an existing database with the old constraint

\c config_db;

-- Drop the old unique constraint on name only
ALTER TABLE feature_flags DROP CONSTRAINT IF EXISTS feature_flags_name_key;

-- Add the new composite unique constraint
ALTER TABLE feature_flags ADD CONSTRAINT uq_feature_flag_name_env UNIQUE (name, environment);

-- Create the feature_flag_history table if it doesn't exist
CREATE TABLE IF NOT EXISTS feature_flag_history (
    id SERIAL PRIMARY KEY,
    feature_flag_id INTEGER REFERENCES feature_flags(id) ON DELETE CASCADE,
    old_is_enabled BOOLEAN,
    new_is_enabled BOOLEAN,
    old_rollout_percentage VARCHAR(255),
    new_rollout_percentage VARCHAR(255),
    old_target_users JSONB,
    new_target_users JSONB,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for the history table
CREATE INDEX IF NOT EXISTS idx_feature_flag_history_flag_id ON feature_flag_history(feature_flag_id);
CREATE INDEX IF NOT EXISTS idx_feature_flag_history_changed_at ON feature_flag_history(changed_at);

-- Create composite index for feature_flags if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_feature_flags_name_env ON feature_flags(name, environment);

