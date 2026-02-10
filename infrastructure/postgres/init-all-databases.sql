-- ============================================================================
-- Complete Database Initialization Script
-- ============================================================================
-- This script creates all databases, schemas, tables, and seed data
-- Run this script once to set up the entire database structure
--
-- IMPORTANT: To run this script, use one of these methods:
--
-- Method 1 (Recommended - using wrapper script):
--   ./infrastructure/postgres/init-all-databases.sh
--
-- Method 2 (Direct execution with error handling):
--   docker compose exec postgres psql -U dhruva_user -d dhruva_platform -f /docker-entrypoint-initdb.d/init-all-databases.sql
-- ============================================================================

-- Continue execution even if some statements fail (e.g., if databases already exist)
\set ON_ERROR_STOP off

-- ============================================================================
-- STEP 1: Create All Databases
-- ============================================================================

-- Note: CREATE DATABASE cannot be executed from a function/DO block in PostgreSQL.
-- These statements must be executed directly. If a database already exists,
-- you'll get an error which will be ignored due to ON_ERROR_STOP being off.

-- Create auth_db
-- (Error will be ignored if database already exists)
CREATE DATABASE auth_db;

-- Create config_db
-- (Error can be ignored if database already exists)
CREATE DATABASE config_db;

-- Create model_management_db
-- (Error can be ignored if database already exists)
CREATE DATABASE model_management_db;

-- Create multi_tenant_db
-- (Error can be ignored if database already exists)
CREATE DATABASE multi_tenant_db;

-- Create unleash database
-- (Error can be ignored if database already exists)
CREATE DATABASE unleash
    WITH ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.utf8'
    LC_CTYPE = 'en_US.utf8'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1;

-- Create alerting_db
-- (Error can be ignored if database already exists)
CREATE DATABASE alerting_db;

-- Grant all privileges on each database to the configured PostgreSQL user
GRANT ALL PRIVILEGES ON DATABASE auth_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE config_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE model_management_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE unleash TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE alerting_db TO dhruva_user;

-- Add comments documenting which service uses each database
COMMENT ON DATABASE auth_db IS 'Authentication & Authorization Service database';
COMMENT ON DATABASE config_db IS 'Configuration Management Service database';
COMMENT ON DATABASE model_management_db IS 'Model Management Service database - stores AI models and services registry';
COMMENT ON DATABASE unleash IS 'Unleash feature flag management database';
COMMENT ON DATABASE alerting_db IS 'Alerting Service database - stores dynamic alert configurations and notification settings';

-- Re-enable error stopping for schema creation (we want to catch real errors)
\set ON_ERROR_STOP on

-- ============================================================================
-- STEP 2: Auth Service Schema (auth_db)
-- ============================================================================

\c auth_db;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255), -- NULL allowed for OAuth users
    is_active BOOLEAN DEFAULT true,
    is_verified BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    full_name VARCHAR(255),
    is_superuser BOOLEAN DEFAULT false,
    last_login TIMESTAMP WITH TIME ZONE,
    preferences JSONB DEFAULT '{}'::jsonb,
    avatar_url VARCHAR(500),
    phone_number VARCHAR(20),
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'en',
    is_tenant BOOLEAN DEFAULT NULL,
    selected_api_key_id INTEGER
);

-- Roles table
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Permissions table
CREATE TABLE IF NOT EXISTS permissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- User roles junction table
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id)
);

-- Role permissions junction table
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER REFERENCES permissions(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, permission_id)
);

-- API keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    key_name VARCHAR(100) NOT NULL,
    key_value_encrypted TEXT,
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP WITH TIME ZONE
);

-- Selected API key reference (per user)
ALTER TABLE users
    ADD CONSTRAINT users_selected_api_key_id_fkey
    FOREIGN KEY (selected_api_key_id) REFERENCES api_keys(id) ON DELETE SET NULL;

-- Create sequence for user_sessions if it doesn't exist
CREATE SEQUENCE IF NOT EXISTS sessions_id_seq;

-- User sessions table (renamed from sessions)
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER DEFAULT nextval('sessions_id_seq') NOT NULL,
    user_id INTEGER,
    session_token TEXT NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    refresh_token TEXT,
    device_info JSONB,
    is_active BOOLEAN DEFAULT true,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    token_type VARCHAR(20) DEFAULT 'access',
    CONSTRAINT sessions_pkey PRIMARY KEY (id),
    CONSTRAINT sessions_session_token_key UNIQUE (session_token),
    CONSTRAINT sessions_refresh_token_key UNIQUE (refresh_token),
    CONSTRAINT user_sessions_refresh_token_key UNIQUE (refresh_token),
    CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- OAuth providers table
CREATE TABLE IF NOT EXISTS oauth_providers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    provider_name VARCHAR(50) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider_name, provider_user_id)
);

-- Enable UUID extension for AI services
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ASR (Automatic Speech Recognition) Tables
CREATE TABLE IF NOT EXISTS asr_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) NOT NULL,
    audio_duration FLOAT,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asr_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES asr_requests(id) ON DELETE CASCADE,
    transcript TEXT NOT NULL,
    confidence_score FLOAT CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    word_timestamps JSONB,
    language_detected VARCHAR(10),
    audio_format VARCHAR(20),
    sample_rate INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- TTS (Text-to-Speech) Tables
CREATE TABLE IF NOT EXISTS tts_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    voice_id VARCHAR(50) NOT NULL,
    language VARCHAR(10) NOT NULL,
    text_length INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tts_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES tts_requests(id) ON DELETE CASCADE,
    audio_file_path TEXT NOT NULL,
    audio_duration FLOAT,
    audio_format VARCHAR(20),
    sample_rate INTEGER,
    bit_rate INTEGER,
    file_size INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- LLM (Large Language Model) Tables
CREATE TABLE IF NOT EXISTS llm_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    input_language VARCHAR(10),
    output_language VARCHAR(10),
    text_length INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS llm_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES llm_requests(id) ON DELETE CASCADE,
    output_text TEXT NOT NULL,
    source_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- NMT (Neural Machine Translation) Tables
CREATE TABLE IF NOT EXISTS nmt_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    source_language VARCHAR(10) NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    text_length INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nmt_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES nmt_requests(id) ON DELETE CASCADE,
    translated_text TEXT NOT NULL,
    confidence_score FLOAT CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    source_text TEXT,
    language_detected VARCHAR(10),
    word_alignments JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Speaker Diarization Tables
CREATE TABLE IF NOT EXISTS speaker_diarization_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    audio_duration FLOAT,
    num_speakers INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS speaker_diarization_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES speaker_diarization_requests(id) ON DELETE CASCADE,
    total_segments INTEGER NOT NULL,
    num_speakers INTEGER NOT NULL,
    speakers JSONB NOT NULL,
    segments JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Language Diarization Tables
CREATE TABLE IF NOT EXISTS language_diarization_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    audio_duration FLOAT,
    target_language VARCHAR(10),
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS language_diarization_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES language_diarization_requests(id) ON DELETE CASCADE,
    total_segments INTEGER NOT NULL,
    segments JSONB NOT NULL,
    target_language VARCHAR(10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Audio Language Detection Tables
CREATE TABLE IF NOT EXISTS audio_lang_detection_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    audio_duration FLOAT,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audio_lang_detection_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES audio_lang_detection_requests(id) ON DELETE CASCADE,
    language_code VARCHAR(50) NOT NULL,
    confidence FLOAT CHECK (confidence >= 0.0 AND confidence <= 1.0),
    all_scores JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for auth_db
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission_id ON role_permissions(permission_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);

-- ============================================================================
-- Migration: Update api_keys table column names for existing databases
-- ============================================================================
-- These migrations handle renaming columns in existing tables:
-- - name -> key_name
-- - last_used_at -> last_used
-- They are idempotent and safe to run multiple times

-- Migration 1: Rename api_keys.name to api_keys.key_name
DO $$
BEGIN
    -- Check if 'name' column exists and 'key_name' doesn't exist
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'api_keys' 
        AND column_name = 'name'
    ) AND NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'api_keys' 
        AND column_name = 'key_name'
    ) THEN
        -- Rename the column from 'name' to 'key_name'
        ALTER TABLE api_keys RENAME COLUMN name TO key_name;
        RAISE NOTICE 'Migrated: Renamed api_keys.name to api_keys.key_name';
    END IF;
END $$;

-- Migration 2: Add permissions column and rename last_used_at to last_used
DO $$
BEGIN
    -- Add permissions column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'api_keys' 
        AND column_name = 'permissions'
    ) THEN
        ALTER TABLE api_keys ADD COLUMN permissions JSONB DEFAULT '[]'::jsonb;
        RAISE NOTICE 'Migrated: Added api_keys.permissions column';
    END IF;
    
    -- Check if 'last_used_at' column exists and 'last_used' doesn't exist
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'api_keys' 
        AND column_name = 'last_used_at'
    ) AND NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'api_keys' 
        AND column_name = 'last_used'
    ) THEN
        -- Rename the column from 'last_used_at' to 'last_used'
        ALTER TABLE api_keys RENAME COLUMN last_used_at TO last_used;
        RAISE NOTICE 'Migrated: Renamed api_keys.last_used_at to api_keys.last_used';
    END IF;
END $$;

-- Migration 3: Add key_value_encrypted column
DO $$
BEGIN
    -- Add key_value_encrypted column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'api_keys' 
        AND column_name = 'key_value_encrypted'
    ) THEN
        ALTER TABLE api_keys ADD COLUMN key_value_encrypted TEXT;
        RAISE NOTICE 'Migrated: Added api_keys.key_value_encrypted column';
    END IF;
END $$;

-- Add comments to document the changes
COMMENT ON COLUMN api_keys.key_name IS 'Name/label for the API key';
COMMENT ON COLUMN api_keys.permissions IS 'Array of permission strings for the API key';
COMMENT ON COLUMN api_keys.key_value_encrypted IS 'Encrypted API key value (encrypted using Fernet)';
CREATE INDEX IF NOT EXISTS idx_user_sessions_session_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_token ON user_sessions(refresh_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_is_active ON user_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token_type ON user_sessions(token_type);
-- Also create legacy indexes for backward compatibility
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_refresh_token ON user_sessions(refresh_token);
CREATE INDEX IF NOT EXISTS idx_sessions_is_active ON user_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_oauth_providers_user_id ON oauth_providers(user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_providers_provider ON oauth_providers(provider_name, provider_user_id);

-- AI Services indexes
CREATE INDEX IF NOT EXISTS idx_asr_requests_user_id ON asr_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_asr_requests_api_key_id ON asr_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_asr_requests_session_id ON asr_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_asr_requests_status ON asr_requests(status);
CREATE INDEX IF NOT EXISTS idx_asr_requests_created_at ON asr_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_asr_requests_user_created ON asr_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_asr_requests_status_created ON asr_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_asr_requests_language ON asr_requests(language);
CREATE INDEX IF NOT EXISTS idx_asr_requests_model_id ON asr_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_asr_requests_model_language ON asr_requests(model_id, language);
CREATE INDEX IF NOT EXISTS idx_asr_results_request_id ON asr_results(request_id);
CREATE INDEX IF NOT EXISTS idx_asr_results_created_at ON asr_results(created_at);

CREATE INDEX IF NOT EXISTS idx_tts_requests_user_id ON tts_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_api_key_id ON tts_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_session_id ON tts_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_status ON tts_requests(status);
CREATE INDEX IF NOT EXISTS idx_tts_requests_created_at ON tts_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_tts_requests_user_created ON tts_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tts_requests_status_created ON tts_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_tts_requests_language ON tts_requests(language);
CREATE INDEX IF NOT EXISTS idx_tts_requests_model_id ON tts_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_model_language ON tts_requests(model_id, language);
CREATE INDEX IF NOT EXISTS idx_tts_requests_voice_id ON tts_requests(voice_id);
CREATE INDEX IF NOT EXISTS idx_tts_results_request_id ON tts_results(request_id);
CREATE INDEX IF NOT EXISTS idx_tts_results_created_at ON tts_results(created_at);

CREATE INDEX IF NOT EXISTS idx_llm_requests_user_id ON llm_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_api_key_id ON llm_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_session_id ON llm_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_status ON llm_requests(status);
CREATE INDEX IF NOT EXISTS idx_llm_requests_created_at ON llm_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_requests_user_created ON llm_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_llm_requests_status_created ON llm_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_llm_requests_input_language ON llm_requests(input_language);
CREATE INDEX IF NOT EXISTS idx_llm_requests_output_language ON llm_requests(output_language);
CREATE INDEX IF NOT EXISTS idx_llm_requests_model_id ON llm_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_llm_results_request_id ON llm_results(request_id);
CREATE INDEX IF NOT EXISTS idx_llm_results_created_at ON llm_results(created_at);

CREATE INDEX IF NOT EXISTS idx_nmt_requests_user_id ON nmt_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_api_key_id ON nmt_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_session_id ON nmt_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_status ON nmt_requests(status);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_created_at ON nmt_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_user_created ON nmt_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_status_created ON nmt_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_source_language ON nmt_requests(source_language);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_target_language ON nmt_requests(target_language);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_model_id ON nmt_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_language_pair ON nmt_requests(source_language, target_language);
CREATE INDEX IF NOT EXISTS idx_nmt_results_request_id ON nmt_results(request_id);
CREATE INDEX IF NOT EXISTS idx_nmt_results_created_at ON nmt_results(created_at);

CREATE INDEX IF NOT EXISTS idx_speaker_diarization_requests_user_id ON speaker_diarization_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_speaker_diarization_requests_api_key_id ON speaker_diarization_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_speaker_diarization_requests_session_id ON speaker_diarization_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_speaker_diarization_requests_status ON speaker_diarization_requests(status);
CREATE INDEX IF NOT EXISTS idx_speaker_diarization_requests_model_id ON speaker_diarization_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_speaker_diarization_requests_created_at ON speaker_diarization_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_speaker_diarization_requests_user_created ON speaker_diarization_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_speaker_diarization_requests_status_created ON speaker_diarization_requests(status, created_at);

CREATE INDEX IF NOT EXISTS idx_speaker_diarization_results_request_id ON speaker_diarization_results(request_id);
CREATE INDEX IF NOT EXISTS idx_speaker_diarization_results_created_at ON speaker_diarization_results(created_at);

CREATE INDEX IF NOT EXISTS idx_language_diarization_requests_user_id ON language_diarization_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_language_diarization_requests_api_key_id ON language_diarization_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_language_diarization_requests_session_id ON language_diarization_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_language_diarization_requests_status ON language_diarization_requests(status);
CREATE INDEX IF NOT EXISTS idx_language_diarization_requests_model_id ON language_diarization_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_language_diarization_requests_created_at ON language_diarization_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_language_diarization_requests_user_created ON language_diarization_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_language_diarization_requests_status_created ON language_diarization_requests(status, created_at);

CREATE INDEX IF NOT EXISTS idx_language_diarization_results_request_id ON language_diarization_results(request_id);
CREATE INDEX IF NOT EXISTS idx_language_diarization_results_created_at ON language_diarization_results(created_at);

CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_requests_user_id ON audio_lang_detection_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_requests_api_key_id ON audio_lang_detection_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_requests_session_id ON audio_lang_detection_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_requests_status ON audio_lang_detection_requests(status);
CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_requests_model_id ON audio_lang_detection_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_requests_created_at ON audio_lang_detection_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_requests_user_created ON audio_lang_detection_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_requests_status_created ON audio_lang_detection_requests(status, created_at);

CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_results_request_id ON audio_lang_detection_results(request_id);
CREATE INDEX IF NOT EXISTS idx_audio_lang_detection_results_created_at ON audio_lang_detection_results(created_at);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns (idempotent: drop if exists, then create)
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_oauth_providers_updated_at ON oauth_providers;
CREATE TRIGGER update_oauth_providers_updated_at BEFORE UPDATE ON oauth_providers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_asr_requests_updated_at ON asr_requests;
CREATE TRIGGER update_asr_requests_updated_at BEFORE UPDATE ON asr_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tts_requests_updated_at ON tts_requests;
CREATE TRIGGER update_tts_requests_updated_at BEFORE UPDATE ON tts_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_nmt_requests_updated_at ON nmt_requests;
CREATE TRIGGER update_nmt_requests_updated_at BEFORE UPDATE ON nmt_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_llm_requests_updated_at ON llm_requests;
CREATE TRIGGER update_llm_requests_updated_at BEFORE UPDATE ON llm_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_speaker_diarization_requests_updated_at ON speaker_diarization_requests;
CREATE TRIGGER update_speaker_diarization_requests_updated_at BEFORE UPDATE ON speaker_diarization_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_language_diarization_requests_updated_at ON language_diarization_requests;
CREATE TRIGGER update_language_diarization_requests_updated_at BEFORE UPDATE ON language_diarization_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_audio_lang_detection_requests_updated_at ON audio_lang_detection_requests;
CREATE TRIGGER update_audio_lang_detection_requests_updated_at BEFORE UPDATE ON audio_lang_detection_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- STEP 3: Config Service Schema (config_db)
-- ============================================================================

\c config_db;

-- Create updated_at trigger function (needed in config_db)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Configurations table
CREATE TABLE IF NOT EXISTS configurations (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) NOT NULL,
    value TEXT NOT NULL,
    environment VARCHAR(50) NOT NULL,
    service_name VARCHAR(100) NOT NULL,
    is_encrypted BOOLEAN DEFAULT false,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(key, environment, service_name)
);

-- Feature flags table
CREATE TABLE IF NOT EXISTS feature_flags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_enabled BOOLEAN DEFAULT false,
    rollout_percentage VARCHAR(255),
    target_users JSONB,
    environment VARCHAR(50) NOT NULL,
    unleash_flag_name VARCHAR(255),
    last_synced_at TIMESTAMP WITH TIME ZONE,
    evaluation_count INTEGER DEFAULT 0,
    last_evaluated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (name, environment)
);

-- Service registry table
CREATE TABLE IF NOT EXISTS service_registry (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) UNIQUE NOT NULL,
    service_url VARCHAR(255) NOT NULL,
    health_check_url VARCHAR(255),
    status VARCHAR(20) DEFAULT 'unknown',
    last_health_check TIMESTAMP WITH TIME ZONE,
    service_metadata JSONB,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Configuration history table
CREATE TABLE IF NOT EXISTS configuration_history (
    id SERIAL PRIMARY KEY,
    configuration_id INTEGER REFERENCES configurations(id) ON DELETE CASCADE,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Feature flag evaluations table
CREATE TABLE IF NOT EXISTS feature_flag_evaluations (
    id SERIAL PRIMARY KEY,
    flag_name VARCHAR(255) NOT NULL,
    user_id VARCHAR(255),
    context JSONB,
    result BOOLEAN,
    variant VARCHAR(100),
    evaluated_value JSONB,
    environment VARCHAR(50) NOT NULL,
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    evaluation_reason VARCHAR(50)
);

-- Create indexes for config_db
CREATE INDEX IF NOT EXISTS idx_configurations_key ON configurations(key);
CREATE INDEX IF NOT EXISTS idx_configurations_environment ON configurations(environment);
CREATE INDEX IF NOT EXISTS idx_configurations_service_name ON configurations(service_name);
CREATE INDEX IF NOT EXISTS idx_feature_flags_name ON feature_flags(name);
CREATE INDEX IF NOT EXISTS idx_feature_flags_environment ON feature_flags(environment);
CREATE INDEX IF NOT EXISTS idx_service_registry_service_name ON service_registry(service_name);
CREATE INDEX IF NOT EXISTS idx_configuration_history_config_id ON configuration_history(configuration_id);
CREATE INDEX IF NOT EXISTS idx_feature_flag_evaluations_flag_name ON feature_flag_evaluations(flag_name);

-- Create triggers for config_db (idempotent: drop if exists, then create)
DROP TRIGGER IF EXISTS update_configurations_updated_at ON configurations;
CREATE TRIGGER update_configurations_updated_at BEFORE UPDATE ON configurations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_feature_flags_updated_at ON feature_flags;
CREATE TRIGGER update_feature_flags_updated_at BEFORE UPDATE ON feature_flags
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_service_registry_updated_at ON service_registry;
CREATE TRIGGER update_service_registry_updated_at BEFORE UPDATE ON service_registry
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- STEP 4: Model Management Service Schema (model_management_db)
-- ============================================================================

\c model_management_db;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create updated_at trigger function (needed in model_management_db)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create version_status enum type for model versioning
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'version_status') THEN
        CREATE TYPE version_status AS ENUM ('ACTIVE', 'DEPRECATED');
    END IF;
END $$;

-- Models table
-- Stores AI model definitions with versioning support
-- model_id is a hash of (name, version), unique constraint on (name, version)
CREATE TABLE IF NOT EXISTS models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id VARCHAR(255) NOT NULL,
    version VARCHAR(100) NOT NULL,
    version_status version_status NOT NULL DEFAULT 'ACTIVE',
    version_status_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    submitted_on BIGINT NOT NULL,
    updated_on BIGINT,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    ref_url VARCHAR(500),
    task JSONB NOT NULL,
    languages JSONB NOT NULL DEFAULT '[]'::jsonb,
    license VARCHAR(255),
    domain JSONB NOT NULL DEFAULT '[]'::jsonb,
    inference_endpoint JSONB NOT NULL,
    benchmarks JSONB,
    submitter JSONB NOT NULL,
    created_by VARCHAR(255) DEFAULT NULL,  -- User ID (string) who created this model
    updated_by VARCHAR(255) DEFAULT NULL,  -- User ID (string) who last updated this model
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Unique constraint on (name, version) for versioning support
    CONSTRAINT uq_name_version UNIQUE (name, version)
);

-- Services table
-- Stores service deployments linked to specific model versions
-- service_id is a hash of (model_name, model_version, service_name)
CREATE TABLE IF NOT EXISTS services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    service_description TEXT,
    hardware_description TEXT,
    published_on BIGINT NOT NULL,
    model_id VARCHAR(255) NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    endpoint VARCHAR(500) NOT NULL,
    api_key VARCHAR(255),
    health_status JSONB,
    benchmarks JSONB,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    published_at BIGINT DEFAULT NULL,
    unpublished_at BIGINT DEFAULT NULL,
    created_by VARCHAR(255) DEFAULT NULL,  -- User ID (string) who created this service
    updated_by VARCHAR(255) DEFAULT NULL,  -- User ID (string) who last updated this service
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Unique constraint on (model_id, model_version, name)
    CONSTRAINT uq_model_id_version_service_name UNIQUE (model_id, model_version, name)
);

-- Create indexes for models table
CREATE INDEX IF NOT EXISTS idx_models_model_id ON models(model_id);
CREATE INDEX IF NOT EXISTS idx_models_name ON models(name);
CREATE INDEX IF NOT EXISTS idx_models_version ON models(version);
CREATE INDEX IF NOT EXISTS idx_models_model_id_version ON models(model_id, version);
CREATE INDEX IF NOT EXISTS idx_models_version_status ON models(version_status);
CREATE INDEX IF NOT EXISTS idx_models_task ON models USING GIN (task);
CREATE INDEX IF NOT EXISTS idx_models_languages ON models USING GIN (languages);
CREATE INDEX IF NOT EXISTS idx_models_domain ON models USING GIN (domain);
CREATE INDEX IF NOT EXISTS idx_models_created_at ON models(created_at);
CREATE INDEX IF NOT EXISTS idx_models_created_by ON models(created_by);

-- Create indexes for services table
CREATE INDEX IF NOT EXISTS idx_services_service_id ON services(service_id);
CREATE INDEX IF NOT EXISTS idx_services_name ON services(name);
CREATE INDEX IF NOT EXISTS idx_services_model_id ON services(model_id);
CREATE INDEX IF NOT EXISTS idx_services_model_id_version ON services(model_id, model_version);
CREATE INDEX IF NOT EXISTS idx_services_is_published ON services(is_published);
CREATE INDEX IF NOT EXISTS idx_services_created_at ON services(created_at);
CREATE INDEX IF NOT EXISTS idx_services_health_status ON services USING GIN (health_status);
CREATE INDEX IF NOT EXISTS idx_services_created_by ON services(created_by);

-- Create trigger for version_status_updated_at
CREATE OR REPLACE FUNCTION update_version_status_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.version_status IS DISTINCT FROM OLD.version_status THEN
        NEW.version_status_updated_at = CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_models_version_status_updated_at ON models;
CREATE TRIGGER update_models_version_status_updated_at
    BEFORE UPDATE ON models
    FOR EACH ROW
    WHEN (NEW.version_status IS DISTINCT FROM OLD.version_status)
    EXECUTE FUNCTION update_version_status_updated_at();

-- Create triggers for updated_at columns
DROP TRIGGER IF EXISTS update_models_updated_at ON models;
CREATE TRIGGER update_models_updated_at BEFORE UPDATE ON models
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_services_updated_at ON services;
CREATE TRIGGER update_services_updated_at BEFORE UPDATE ON services
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE models IS 'AI model registry with versioning support';
COMMENT ON COLUMN models.model_id IS 'Hash-based unique identifier derived from (name, version)';
COMMENT ON COLUMN models.version_status IS 'Status of the model version: ACTIVE or DEPRECATED';
COMMENT ON COLUMN models.version_status_updated_at IS 'Timestamp when the version status was last updated';
COMMENT ON COLUMN models.task IS 'JSONB containing task type and configuration';
COMMENT ON COLUMN models.languages IS 'JSONB array of supported language codes';
COMMENT ON COLUMN models.domain IS 'JSONB array of domain tags';
COMMENT ON COLUMN models.inference_endpoint IS 'JSONB containing endpoint configuration';
COMMENT ON COLUMN models.submitter IS 'JSONB containing submitter information';

COMMENT ON TABLE services IS 'Service deployments linked to specific model versions';
COMMENT ON COLUMN services.service_id IS 'Hash-based unique identifier derived from (model_name, model_version, service_name)';
COMMENT ON COLUMN services.model_version IS 'Version of the model associated with this service';
COMMENT ON COLUMN services.is_published IS 'Whether the service is published and publicly available';
COMMENT ON COLUMN services.published_at IS 'Unix timestamp when the service was published';
COMMENT ON COLUMN services.unpublished_at IS 'Unix timestamp when the service was unpublished';

-- ----------------------------------------------------------------------------
-- A/B Testing: experiment_status enum and tables
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'experiment_status') THEN
        CREATE TYPE experiment_status AS ENUM ('DRAFT', 'RUNNING', 'PAUSED', 'COMPLETED', 'CANCELLED');
    END IF;
END $$;

-- Experiments table (A/B testing)
CREATE TABLE IF NOT EXISTS experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status experiment_status NOT NULL DEFAULT 'DRAFT',
    task_type JSONB DEFAULT NULL,
    languages JSONB DEFAULT NULL,
    start_date TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    end_date TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    created_by VARCHAR(255) DEFAULT NULL,
    updated_by VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
);

-- Experiment variants table (model/service variants per experiment)
CREATE TABLE IF NOT EXISTS experiment_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    variant_name VARCHAR(255) NOT NULL,
    service_id VARCHAR(255) NOT NULL REFERENCES services(service_id) ON DELETE CASCADE,
    traffic_percentage BIGINT NOT NULL,
    description TEXT DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_experiment_service UNIQUE (experiment_id, service_id)
);

-- Experiment metrics table (daily aggregation per variant)
CREATE TABLE IF NOT EXISTS experiment_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    variant_id UUID NOT NULL REFERENCES experiment_variants(id) ON DELETE CASCADE,
    request_count BIGINT NOT NULL DEFAULT 0,
    success_count BIGINT NOT NULL DEFAULT 0,
    error_count BIGINT NOT NULL DEFAULT 0,
    avg_latency_ms BIGINT DEFAULT NULL,
    custom_metrics JSONB DEFAULT NULL,
    metric_date TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_experiment_variant_date UNIQUE (experiment_id, variant_id, metric_date)
);

-- Indexes for experiments
CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
CREATE INDEX IF NOT EXISTS idx_experiments_task_type ON experiments USING GIN (task_type);
CREATE INDEX IF NOT EXISTS idx_experiments_languages ON experiments USING GIN (languages);
CREATE INDEX IF NOT EXISTS idx_experiments_start_date ON experiments(start_date);
CREATE INDEX IF NOT EXISTS idx_experiments_end_date ON experiments(end_date);
CREATE INDEX IF NOT EXISTS idx_experiments_created_at ON experiments(created_at);

-- Indexes for experiment_variants
CREATE INDEX IF NOT EXISTS idx_experiment_variants_experiment_id ON experiment_variants(experiment_id);
CREATE INDEX IF NOT EXISTS idx_experiment_variants_service_id ON experiment_variants(service_id);

-- Indexes for experiment_metrics
CREATE INDEX IF NOT EXISTS idx_experiment_metrics_experiment_id ON experiment_metrics(experiment_id);
CREATE INDEX IF NOT EXISTS idx_experiment_metrics_variant_id ON experiment_metrics(variant_id);
CREATE INDEX IF NOT EXISTS idx_experiment_metrics_metric_date ON experiment_metrics(metric_date);

-- Triggers for updated_at on A/B tables
DROP TRIGGER IF EXISTS update_experiments_updated_at ON experiments;
CREATE TRIGGER update_experiments_updated_at BEFORE UPDATE ON experiments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_experiment_variants_updated_at ON experiment_variants;
CREATE TRIGGER update_experiment_variants_updated_at BEFORE UPDATE ON experiment_variants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_experiment_metrics_updated_at ON experiment_metrics;
CREATE TRIGGER update_experiment_metrics_updated_at BEFORE UPDATE ON experiment_metrics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for A/B testing tables
COMMENT ON TABLE experiments IS 'A/B testing experiments with traffic split across model variants';
COMMENT ON COLUMN experiments.status IS 'DRAFT, RUNNING, PAUSED, COMPLETED, or CANCELLED';
COMMENT ON COLUMN experiments.task_type IS 'Optional JSONB list of task types to filter (e.g. asr, nmt, tts)';
COMMENT ON COLUMN experiments.languages IS 'Optional JSONB list of language codes to filter; null/empty = all languages';
COMMENT ON TABLE experiment_variants IS 'Model/service variants and traffic percentage per experiment';
COMMENT ON TABLE experiment_metrics IS 'Daily aggregated metrics per experiment variant';

-- Ensure experiment_status enum has all values (for DBs where enum was created by older app version)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'experiment_status') THEN
        ALTER TYPE experiment_status ADD VALUE IF NOT EXISTS 'PAUSED';
        ALTER TYPE experiment_status ADD VALUE IF NOT EXISTS 'COMPLETED';
        ALTER TYPE experiment_status ADD VALUE IF NOT EXISTS 'CANCELLED';
    END IF;
END $$;

-- ============================================================================
-- STEP 5: Multi Tenant Feature Schema (multi_tenant_db)
-- ============================================================================

\c multi_tenant_db;

-- ----------------------------------------------------------------------------
-- Table: tenants
-- Description: Master tenants table (stored in public schema)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) UNIQUE NOT NULL,
    organization_name VARCHAR(255) NOT NULL,
    contact_email VARCHAR(320) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,
    schema_name VARCHAR(255) UNIQUE NOT NULL,
    user_id INTEGER NULL,
    subscriptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    quotas JSONB NOT NULL DEFAULT '{}'::jsonb,
    usage JSONB NOT NULL DEFAULT '{}'::jsonb,
    temp_admin_username VARCHAR(128) NULL,
    temp_admin_password_hash VARCHAR(512) NULL,
    expiry_date TIMESTAMP NULL DEFAULT (NOW() + INTERVAL '365 days'),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for tenants table
CREATE INDEX IF NOT EXISTS idx_tenants_contact_email ON tenants(contact_email);
CREATE INDEX IF NOT EXISTS idx_tenants_user_id ON tenants(user_id);

-- ----------------------------------------------------------------------------
-- Table: tenant_billing_records
-- Description: Billing records for tenants
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_billing_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    billing_customer_id VARCHAR(255) NULL,
    cost NUMERIC(20, 10) NOT NULL DEFAULT 0.00,
    billing_status VARCHAR(50) NOT NULL DEFAULT 'UNPAID',
    suspension_reason VARCHAR(512) NULL,
    suspended_until TIMESTAMP NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_tenant_billing_records_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- Table: tenant_audit_logs
-- Description: Audit logs for tenant actions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    actor VARCHAR(50) NOT NULL DEFAULT 'system',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_tenant_audit_logs_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE
);

-- Indexes for tenant_audit_logs table
CREATE INDEX IF NOT EXISTS idx_tenant_audit_logs_tenant_id ON tenant_audit_logs(tenant_id);

-- ----------------------------------------------------------------------------
-- Table: tenant_email_verifications
-- Description: Email verification tokens for tenants
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_email_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    token VARCHAR(512) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    verified_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_tenant_email_verifications_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- Table: service_config
-- Description: Service configuration and pricing
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_config (
    id BIGSERIAL PRIMARY KEY,
    service_name VARCHAR(50) UNIQUE NOT NULL,
    unit_type VARCHAR(50) NOT NULL,
    price_per_unit NUMERIC(10, 6) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- Table: tenant_users
-- Description: Users associated with tenants
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    tenant_uuid UUID NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(320) NOT NULL,
    subscriptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_tenant_users_tenant_uuid 
        FOREIGN KEY (tenant_uuid) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_tenant_users_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(tenant_id) 
        ON DELETE CASCADE
);

-- Indexes for tenant_users table
CREATE INDEX IF NOT EXISTS idx_tenant_users_user_id ON tenant_users(user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_users_tenant_id ON tenant_users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_users_email ON tenant_users(email);

-- ----------------------------------------------------------------------------
-- Table: user_billing_records
-- Description: Billing records for individual tenant users
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_billing_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    service_name VARCHAR(50) NOT NULL,
    service_id BIGINT NOT NULL,
    cost NUMERIC(20, 10) NOT NULL DEFAULT 0.00,
    billing_period DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_user_billing_records_user_id 
        FOREIGN KEY (user_id) 
        REFERENCES tenant_users(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_user_billing_records_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(tenant_id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_user_billing_records_service_id 
        FOREIGN KEY (service_id) 
        REFERENCES service_config(id)
);

-- ============================================================================
-- Create Triggers for updated_at Timestamps
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to all tables with updated_at column
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenant_billing_records_updated_at
    BEFORE UPDATE ON tenant_billing_records
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenant_audit_logs_updated_at
    BEFORE UPDATE ON tenant_audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_service_config_updated_at
    BEFORE UPDATE ON service_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenant_users_updated_at
    BEFORE UPDATE ON tenant_users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_billing_records_updated_at
    BEFORE UPDATE ON user_billing_records
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Add Comments for Documentation
-- ============================================================================

COMMENT ON TABLE tenants IS 'Master tenants table storing tenant information in public schema';
COMMENT ON COLUMN tenants.tenant_id IS 'User-provided unique tenant identifier';
COMMENT ON COLUMN tenants.schema_name IS 'Generated database schema name for tenant-specific tables';
COMMENT ON COLUMN tenants.subscriptions IS 'Array of service names the tenant is subscribed to (e.g., ["tts", "asr", "nmt"])';
COMMENT ON COLUMN tenants.quotas IS 'JSON object with quota limits (e.g., {"api_calls_per_day": 10000, "storage_gb": 10})';
COMMENT ON COLUMN tenants.usage IS 'JSON object with current usage metrics (e.g., {"api_calls_today": 500, "storage_used_gb": 2.5})';

COMMENT ON TABLE tenant_billing_records IS 'Billing records for tenant-level billing';
COMMENT ON TABLE tenant_audit_logs IS 'Audit trail of all tenant-related actions';
COMMENT ON TABLE tenant_email_verifications IS 'Email verification tokens for tenant registration';
COMMENT ON TABLE service_config IS 'Service configuration and pricing information';
COMMENT ON TABLE tenant_users IS 'Users associated with tenants (many-to-one relationship)';
COMMENT ON TABLE user_billing_records IS 'Billing records for individual tenant users';

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Multi-tenant database schema initialization completed successfully';
    RAISE NOTICE 'Created tables: tenants, tenant_billing_records, tenant_audit_logs, tenant_email_verifications, service_config, tenant_users, user_billing_records';
    RAISE NOTICE 'All tables are in the public schema of multi_tenant_db database';
END $$;

-- ============================================================================
-- STEP 6: Alerting Service Schema (alerting_db)
-- ============================================================================

\c alerting_db;

-- Alert Definitions Table
-- Stores complete PromQL expressions per customer with all metadata
CREATE TABLE IF NOT EXISTS alert_definitions (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL, -- Organization identifier (e.g., 'irctc', 'kisanmitra')
    name VARCHAR(255) NOT NULL, -- Alert name (e.g., 'HighLatency')
    description TEXT,
    promql_expr TEXT NOT NULL, -- Complete PromQL expression with organization filter and threshold embedded
    category VARCHAR(50) NOT NULL DEFAULT 'application', -- 'application' or 'infrastructure'
    severity VARCHAR(20) NOT NULL, -- 'critical', 'warning', 'info'
    urgency VARCHAR(20) DEFAULT 'medium', -- 'high', 'medium', 'low'
    alert_type VARCHAR(50), -- 'latency', 'error_rate', 'cpu', etc.
    scope VARCHAR(50), -- 'all_services', 'per_service', 'per_endpoint', 'cluster', etc.
    evaluation_interval VARCHAR(20) DEFAULT '30s', -- Prometheus evaluation interval
    for_duration VARCHAR(20) DEFAULT '5m', -- Duration before alert fires
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    -- Ensure unique alert name per organization
    CONSTRAINT unique_organization_alert_name UNIQUE (organization, name)
);

-- Annotations for alert definitions (summary, description, impact, action)
CREATE TABLE IF NOT EXISTS alert_annotations (
    id SERIAL PRIMARY KEY,
    alert_definition_id INTEGER NOT NULL REFERENCES alert_definitions(id) ON DELETE CASCADE,
    annotation_key VARCHAR(50) NOT NULL, -- 'summary', 'description', 'impact', 'action'
    annotation_value TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_alert_annotation_key UNIQUE (alert_definition_id, annotation_key)
);

-- Notification Receivers Table
-- Stores email configurations per customer
CREATE TABLE IF NOT EXISTS notification_receivers (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL,
    receiver_name VARCHAR(255) NOT NULL, -- Unique receiver name per customer
    -- Email configuration
    email_to TEXT[] NOT NULL, -- Array of email addresses (required)
    email_subject_template TEXT, -- Custom subject template
    email_body_template TEXT, -- Custom HTML body template
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    -- Ensure unique receiver name per organization
    CONSTRAINT unique_organization_receiver_name UNIQUE (organization, receiver_name)
);

-- Routing Rules Table
-- Defines which alerts go to which receivers based on severity/category
CREATE TABLE IF NOT EXISTS routing_rules (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    receiver_id INTEGER NOT NULL REFERENCES notification_receivers(id) ON DELETE CASCADE,
    -- Match conditions (all must match for rule to apply)
    match_severity VARCHAR(20), -- 'critical', 'warning', 'info', or NULL (matches all)
    match_category VARCHAR(50), -- 'application', 'infrastructure', or NULL (matches all)
    match_alert_type VARCHAR(50), -- Specific alert type or NULL (matches all)
    -- Routing behavior
    group_by TEXT[], -- Array of label names to group by (e.g., ['alertname', 'category', 'severity'])
    group_wait VARCHAR(20) DEFAULT '10s',
    group_interval VARCHAR(20) DEFAULT '10s',
    repeat_interval VARCHAR(20) DEFAULT '12h',
    continue_routing BOOLEAN DEFAULT false, -- If true, continue to next matching rule
    priority INTEGER DEFAULT 100, -- Lower number = higher priority (evaluated first)
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    -- Ensure unique rule name per organization
    CONSTRAINT unique_organization_rule_name UNIQUE (organization, rule_name)
);

-- Audit Log Table
-- Records all changes to alert configurations for compliance and troubleshooting
CREATE TABLE IF NOT EXISTS alert_config_audit_log (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100),
    table_name VARCHAR(50) NOT NULL, -- 'alert_definitions', 'notification_receivers', 'routing_rules'
    record_id INTEGER NOT NULL,
    operation VARCHAR(20) NOT NULL, -- 'CREATE', 'UPDATE', 'DELETE'
    changed_by VARCHAR(100) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Store before/after values as JSON for detailed audit trail
    before_values JSONB,
    after_values JSONB,
    change_description TEXT
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_alert_definitions_organization ON alert_definitions(organization);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_enabled ON alert_definitions(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_category ON alert_definitions(category);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_severity ON alert_definitions(severity);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_organization_enabled ON alert_definitions(organization, enabled);

CREATE INDEX IF NOT EXISTS idx_alert_annotations_alert_def_id ON alert_annotations(alert_definition_id);

CREATE INDEX IF NOT EXISTS idx_notification_receivers_organization ON notification_receivers(organization);
CREATE INDEX IF NOT EXISTS idx_notification_receivers_enabled ON notification_receivers(enabled);

CREATE INDEX IF NOT EXISTS idx_routing_rules_organization ON routing_rules(organization);
CREATE INDEX IF NOT EXISTS idx_routing_rules_receiver_id ON routing_rules(receiver_id);
CREATE INDEX IF NOT EXISTS idx_routing_rules_enabled ON routing_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_routing_rules_priority ON routing_rules(priority);
CREATE INDEX IF NOT EXISTS idx_routing_rules_match_severity ON routing_rules(match_severity);
CREATE INDEX IF NOT EXISTS idx_routing_rules_match_category ON routing_rules(match_category);

CREATE INDEX IF NOT EXISTS idx_audit_log_organization ON alert_config_audit_log(organization);
CREATE INDEX IF NOT EXISTS idx_audit_log_table_record ON alert_config_audit_log(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON alert_config_audit_log(changed_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_by ON alert_config_audit_log(changed_by);

-- Create trigger function for updated_at
CREATE OR REPLACE FUNCTION update_alert_config_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at columns
CREATE TRIGGER update_alert_definitions_updated_at 
    BEFORE UPDATE ON alert_definitions
    FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();

CREATE TRIGGER update_alert_annotations_updated_at 
    BEFORE UPDATE ON alert_annotations
    FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();

CREATE TRIGGER update_notification_receivers_updated_at 
    BEFORE UPDATE ON notification_receivers
    FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();

CREATE TRIGGER update_routing_rules_updated_at 
    BEFORE UPDATE ON routing_rules
    FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();

-- Create audit log trigger function
CREATE OR REPLACE FUNCTION log_alert_config_changes()
RETURNS TRIGGER AS $$
DECLARE
    v_organization VARCHAR(100);
    v_table_name VARCHAR(50);
    v_record_id INTEGER;
    v_operation VARCHAR(20);
    v_changed_by VARCHAR(100);
    v_before_values JSONB;
    v_after_values JSONB;
BEGIN
    -- Determine table name and organization based on which table triggered
    IF TG_TABLE_NAME = 'alert_definitions' THEN
        v_table_name := 'alert_definitions';
        v_record_id := COALESCE(NEW.id, OLD.id);
        v_organization := COALESCE(NEW.organization, OLD.organization);
        v_changed_by := COALESCE(NEW.updated_by, NEW.created_by, OLD.updated_by, OLD.created_by, 'system');
        
        IF TG_OP = 'INSERT' THEN
            v_operation := 'CREATE';
            v_after_values := to_jsonb(NEW);
            v_before_values := NULL;
        ELSIF TG_OP = 'UPDATE' THEN
            v_operation := 'UPDATE';
            v_before_values := to_jsonb(OLD);
            v_after_values := to_jsonb(NEW);
        ELSIF TG_OP = 'DELETE' THEN
            v_operation := 'DELETE';
            v_before_values := to_jsonb(OLD);
            v_after_values := NULL;
        END IF;
        
    ELSIF TG_TABLE_NAME = 'notification_receivers' THEN
        v_table_name := 'notification_receivers';
        v_record_id := COALESCE(NEW.id, OLD.id);
        v_organization := COALESCE(NEW.organization, OLD.organization);
        -- notification_receivers doesn't have updated_by column, only created_by
        v_changed_by := COALESCE(NEW.created_by, OLD.created_by, 'system');
        
        IF TG_OP = 'INSERT' THEN
            v_operation := 'CREATE';
            v_after_values := to_jsonb(NEW);
            v_before_values := NULL;
        ELSIF TG_OP = 'UPDATE' THEN
            v_operation := 'UPDATE';
            v_before_values := to_jsonb(OLD);
            v_after_values := to_jsonb(NEW);
        ELSIF TG_OP = 'DELETE' THEN
            v_operation := 'DELETE';
            v_before_values := to_jsonb(OLD);
            v_after_values := NULL;
        END IF;
        
    ELSIF TG_TABLE_NAME = 'routing_rules' THEN
        v_table_name := 'routing_rules';
        v_record_id := COALESCE(NEW.id, OLD.id);
        v_organization := COALESCE(NEW.organization, OLD.organization);
        -- routing_rules doesn't have updated_by column, only created_by
        v_changed_by := COALESCE(NEW.created_by, OLD.created_by, 'system');
        
        IF TG_OP = 'INSERT' THEN
            v_operation := 'CREATE';
            v_after_values := to_jsonb(NEW);
            v_before_values := NULL;
        ELSIF TG_OP = 'UPDATE' THEN
            v_operation := 'UPDATE';
            v_before_values := to_jsonb(OLD);
            v_after_values := to_jsonb(NEW);
        ELSIF TG_OP = 'DELETE' THEN
            v_operation := 'DELETE';
            v_before_values := to_jsonb(OLD);
            v_after_values := NULL;
        END IF;
    END IF;
    
    -- Insert audit log entry
    INSERT INTO alert_config_audit_log (
        organization,
        table_name,
        record_id,
        operation,
        changed_by,
        before_values,
        after_values
    ) VALUES (
        v_organization,
        v_table_name,
        v_record_id,
        v_operation,
        v_changed_by,
        v_before_values,
        v_after_values
    );
    
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create audit triggers
CREATE TRIGGER audit_alert_definitions_changes
    AFTER INSERT OR UPDATE OR DELETE ON alert_definitions
    FOR EACH ROW EXECUTE FUNCTION log_alert_config_changes();

CREATE TRIGGER audit_notification_receivers_changes
    AFTER INSERT OR UPDATE OR DELETE ON notification_receivers
    FOR EACH ROW EXECUTE FUNCTION log_alert_config_changes();

CREATE TRIGGER audit_routing_rules_changes
    AFTER INSERT OR UPDATE OR DELETE ON routing_rules
    FOR EACH ROW EXECUTE FUNCTION log_alert_config_changes();

-- Add comments for documentation
COMMENT ON TABLE alert_definitions IS 'Stores organization-specific alert definitions with complete PromQL expressions';
COMMENT ON TABLE alert_annotations IS 'Stores annotations (summary, description, impact, action) for alert definitions';
COMMENT ON TABLE notification_receivers IS 'Stores notification channel configurations (email) per organization';
COMMENT ON TABLE routing_rules IS 'Defines routing rules that match alerts to receivers based on severity/category';
COMMENT ON TABLE alert_config_audit_log IS 'Audit trail of all changes to alert configurations for compliance';

-- ============================================================================
-- Seed Data: Sample Models and Services for Each Task Type
-- ============================================================================
-- These are placeholder models and services for testing purposes.
-- Users should UPDATE the endpoint URLs to point to their actual services.
-- 
-- Task Types: asr, tts, nmt, llm, transliteration, language-detection,
--             speaker-diarization, audio-lang-detection, language-diarization,
--             ocr, ner
-- ============================================================================

-- Helper function to generate model_id hash (matches Python implementation)
CREATE OR REPLACE FUNCTION generate_model_id(model_name TEXT, version TEXT) 
RETURNS VARCHAR(32) AS $$
BEGIN
    RETURN SUBSTRING(encode(sha256((LOWER(TRIM(model_name)) || ':' || LOWER(TRIM(version)))::bytea), 'hex'), 1, 32);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Helper function to generate service_id hash (matches Python implementation)
CREATE OR REPLACE FUNCTION generate_service_id(model_name TEXT, model_version TEXT, service_name TEXT) 
RETURNS VARCHAR(32) AS $$
BEGIN
    RETURN SUBSTRING(encode(sha256((LOWER(TRIM(model_name)) || ':' || LOWER(TRIM(model_version)) || ':' || LOWER(TRIM(service_name)))::bytea), 'hex'), 1, 32);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Current timestamp in epoch milliseconds
DO $$
DECLARE
    current_epoch BIGINT := EXTRACT(EPOCH FROM NOW()) * 1000;
BEGIN
    -- ========================================================================
    -- ASR (Automatic Speech Recognition) Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('ASR-Conformer-Hindi', '1.0.0'),
        '1.0.0',
        'ASR-Conformer-Hindi',
        'Automatic Speech Recognition model for Hindi language using Conformer architecture. UPDATE ENDPOINT before use.',
        '{"type": "asr"}'::jsonb,
        '["hi", "en"]'::jsonb,
        '["general", "conversational"]'::jsonb,
        'Apache-2.0',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8001/asr/v1/recognize"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('ASR-Conformer-Hindi', '1.0.0', 'asr-hindi-prod'),
        'asr-hindi-prod',
        generate_model_id('ASR-Conformer-Hindi', '1.0.0'),
        '1.0.0',
        'http://localhost:8001/asr/v1/recognize',
        'Production ASR service for Hindi. UPDATE ENDPOINT to your actual service URL.',
        'GPU: NVIDIA T4, RAM: 16GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- TTS (Text-to-Speech) Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('TTS-FastPitch-Hindi', '1.0.0'),
        '1.0.0',
        'TTS-FastPitch-Hindi',
        'Text-to-Speech model for Hindi language using FastPitch architecture. UPDATE ENDPOINT before use.',
        '{"type": "tts"}'::jsonb,
        '["hi"]'::jsonb,
        '["general"]'::jsonb,
        'MIT',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8002/tts/v1/synthesize"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('TTS-FastPitch-Hindi', '1.0.0', 'tts-hindi-prod'),
        'tts-hindi-prod',
        generate_model_id('TTS-FastPitch-Hindi', '1.0.0'),
        '1.0.0',
        'http://localhost:8002/tts/v1/synthesize',
        'Production TTS service for Hindi. UPDATE ENDPOINT to your actual service URL.',
        'GPU: NVIDIA T4, RAM: 16GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- NMT (Neural Machine Translation) Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('NMT-IndicTrans2-En-Hi', '1.0.0'),
        '1.0.0',
        'NMT-IndicTrans2-En-Hi',
        'Neural Machine Translation model for English to Hindi using IndicTrans2. UPDATE ENDPOINT before use.',
        '{"type": "nmt"}'::jsonb,
        '["en", "hi"]'::jsonb,
        '["general", "news", "conversational"]'::jsonb,
        'MIT',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8003/nmt/v1/translate"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('NMT-IndicTrans2-En-Hi', '1.0.0', 'nmt-en-hi-prod'),
        'nmt-en-hi-prod',
        generate_model_id('NMT-IndicTrans2-En-Hi', '1.0.0'),
        '1.0.0',
        'http://localhost:8003/nmt/v1/translate',
        'Production NMT service for English-Hindi translation. UPDATE ENDPOINT to your actual service URL.',
        'GPU: NVIDIA A10, RAM: 32GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- LLM (Large Language Model) Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('LLM-Indic-Chat', '1.0.0'),
        '1.0.0',
        'LLM-Indic-Chat',
        'Large Language Model for Indic languages chat/completion. UPDATE ENDPOINT before use.',
        '{"type": "llm"}'::jsonb,
        '["hi", "en", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "or"]'::jsonb,
        '["general", "conversational", "qa"]'::jsonb,
        'Apache-2.0',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8004/llm/v1/completions"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('LLM-Indic-Chat', '1.0.0', 'llm-indic-prod'),
        'llm-indic-prod',
        generate_model_id('LLM-Indic-Chat', '1.0.0'),
        '1.0.0',
        'http://localhost:8004/llm/v1/completions',
        'Production LLM service for Indic languages. UPDATE ENDPOINT to your actual service URL.',
        'GPU: NVIDIA A100, RAM: 80GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- Transliteration Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('Transliteration-IndicXlit', '1.0.0'),
        '1.0.0',
        'Transliteration-IndicXlit',
        'Transliteration model for Indic scripts using IndicXlit. UPDATE ENDPOINT before use.',
        '{"type": "transliteration"}'::jsonb,
        '["hi", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "or"]'::jsonb,
        '["general"]'::jsonb,
        'MIT',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8005/transliteration/v1/transliterate"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('Transliteration-IndicXlit', '1.0.0', 'xlit-indic-prod'),
        'xlit-indic-prod',
        generate_model_id('Transliteration-IndicXlit', '1.0.0'),
        '1.0.0',
        'http://localhost:8005/transliteration/v1/transliterate',
        'Production Transliteration service. UPDATE ENDPOINT to your actual service URL.',
        'CPU: 8 cores, RAM: 16GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- Language Detection Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('LangDetect-IndicLID', '1.0.0'),
        '1.0.0',
        'LangDetect-IndicLID',
        'Text language detection model for Indic languages. UPDATE ENDPOINT before use.',
        '{"type": "language-detection"}'::jsonb,
        '["hi", "en", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "or"]'::jsonb,
        '["general"]'::jsonb,
        'MIT',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8006/langdetect/v1/detect"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('LangDetect-IndicLID', '1.0.0', 'langdetect-prod'),
        'langdetect-prod',
        generate_model_id('LangDetect-IndicLID', '1.0.0'),
        '1.0.0',
        'http://localhost:8006/langdetect/v1/detect',
        'Production Language Detection service. UPDATE ENDPOINT to your actual service URL.',
        'CPU: 4 cores, RAM: 8GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- Speaker Diarization Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('SpeakerDiarization-Pyannote', '1.0.0'),
        '1.0.0',
        'SpeakerDiarization-Pyannote',
        'Speaker diarization model using Pyannote. UPDATE ENDPOINT before use.',
        '{"type": "speaker-diarization"}'::jsonb,
        '["*"]'::jsonb,
        '["general", "meetings", "podcasts"]'::jsonb,
        'MIT',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8007/speaker-diarization/v1/diarize"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('SpeakerDiarization-Pyannote', '1.0.0', 'speaker-diarize-prod'),
        'speaker-diarize-prod',
        generate_model_id('SpeakerDiarization-Pyannote', '1.0.0'),
        '1.0.0',
        'http://localhost:8007/speaker-diarization/v1/diarize',
        'Production Speaker Diarization service. UPDATE ENDPOINT to your actual service URL.',
        'GPU: NVIDIA T4, RAM: 16GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- Audio Language Detection Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('AudioLangDetect-Whisper', '1.0.0'),
        '1.0.0',
        'AudioLangDetect-Whisper',
        'Audio language detection model using Whisper. UPDATE ENDPOINT before use.',
        '{"type": "audio-lang-detection"}'::jsonb,
        '["hi", "en", "ta", "te", "bn", "mr"]'::jsonb,
        '["general"]'::jsonb,
        'MIT',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8008/audio-langdetect/v1/detect"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('AudioLangDetect-Whisper', '1.0.0', 'audio-langdetect-prod'),
        'audio-langdetect-prod',
        generate_model_id('AudioLangDetect-Whisper', '1.0.0'),
        '1.0.0',
        'http://localhost:8008/audio-langdetect/v1/detect',
        'Production Audio Language Detection service. UPDATE ENDPOINT to your actual service URL.',
        'GPU: NVIDIA T4, RAM: 16GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- Language Diarization Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('LangDiarization-MultiLang', '1.0.0'),
        '1.0.0',
        'LangDiarization-MultiLang',
        'Language diarization model for multi-language audio. UPDATE ENDPOINT before use.',
        '{"type": "language-diarization"}'::jsonb,
        '["hi", "en", "ta", "te"]'::jsonb,
        '["code-switching", "multilingual"]'::jsonb,
        'Apache-2.0',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8009/lang-diarization/v1/diarize"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('LangDiarization-MultiLang', '1.0.0', 'lang-diarize-prod'),
        'lang-diarize-prod',
        generate_model_id('LangDiarization-MultiLang', '1.0.0'),
        '1.0.0',
        'http://localhost:8009/lang-diarization/v1/diarize',
        'Production Language Diarization service. UPDATE ENDPOINT to your actual service URL.',
        'GPU: NVIDIA T4, RAM: 16GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- OCR (Optical Character Recognition) Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('OCR-IndicOCR', '1.0.0'),
        '1.0.0',
        'OCR-IndicOCR',
        'Optical Character Recognition model for Indic scripts. UPDATE ENDPOINT before use.',
        '{"type": "ocr"}'::jsonb,
        '["hi", "ta", "te", "bn", "mr", "gu", "kn", "ml"]'::jsonb,
        '["documents", "handwritten", "printed"]'::jsonb,
        'Apache-2.0',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8010/ocr/v1/recognize"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('OCR-IndicOCR', '1.0.0', 'ocr-indic-prod'),
        'ocr-indic-prod',
        generate_model_id('OCR-IndicOCR', '1.0.0'),
        '1.0.0',
        'http://localhost:8010/ocr/v1/recognize',
        'Production OCR service for Indic scripts. UPDATE ENDPOINT to your actual service URL.',
        'GPU: NVIDIA T4, RAM: 16GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

    -- ========================================================================
    -- NER (Named Entity Recognition) Model and Service
    -- ========================================================================
    INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
    VALUES (
        generate_model_id('NER-IndicNER', '1.0.0'),
        '1.0.0',
        'NER-IndicNER',
        'Named Entity Recognition model for Indic languages. UPDATE ENDPOINT before use.',
        '{"type": "ner"}'::jsonb,
        '["hi", "en", "ta", "te", "bn", "mr"]'::jsonb,
        '["general", "news", "legal"]'::jsonb,
        'MIT',
        '{"schema": {"request": {}, "response": {}}, "callbackUrl": "http://localhost:8011/ner/v1/extract"}'::jsonb,
        '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
        current_epoch,
        'ACTIVE'
    ) ON CONFLICT (name, version) DO NOTHING;

    INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
    VALUES (
        generate_service_id('NER-IndicNER', '1.0.0', 'ner-indic-prod'),
        'ner-indic-prod',
        generate_model_id('NER-IndicNER', '1.0.0'),
        '1.0.0',
        'http://localhost:8011/ner/v1/extract',
        'Production NER service for Indic languages. UPDATE ENDPOINT to your actual service URL.',
        'CPU: 8 cores, RAM: 16GB',
        current_epoch,
        false
    ) ON CONFLICT (model_id, model_version, name) DO NOTHING;

END $$;

-- Log seed data completion
DO $$
BEGIN
    RAISE NOTICE 'Model Management seed data inserted: 11 models and 11 services for all task types';
    RAISE NOTICE 'IMPORTANT: Update the endpoint URLs to point to your actual services before publishing';
END $$;

-- ============================================================================
-- STEP 5: Auth Service Seed Data (auth_db)
-- ============================================================================

\c auth_db;

-- Insert default roles
INSERT INTO roles (name, description) VALUES
('ADMIN', 'Administrator with full system access'),
('USER', 'Regular user with standard permissions'),
('GUEST', 'Guest user with read-only access'),
('MODERATOR', 'Moderator with elevated permissions')
ON CONFLICT (name) DO NOTHING;

-- Insert default permissions
INSERT INTO permissions (name, resource, action) VALUES
('users.create', 'users', 'create'),
('users.read', 'users', 'read'),
('users.update', 'users', 'update'),
('users.delete', 'users', 'delete'),
('configs.create', 'configurations', 'create'),
('configs.read', 'configurations', 'read'),
('configs.update', 'configurations', 'update'),
('configs.delete', 'configurations', 'delete'),
('metrics.read', 'metrics', 'read'),
('metrics.export', 'metrics', 'export'),
('alerts.create', 'alerts', 'create'),
('alerts.read', 'alerts', 'read'),
('alerts.update', 'alerts', 'update'),
('alerts.delete', 'alerts', 'delete'),
('dashboards.create', 'dashboards', 'create'),
('dashboards.read', 'dashboards', 'read'),
('dashboards.update', 'dashboards', 'update'),
('dashboards.delete', 'dashboards', 'delete'),
('asr.inference', 'asr', 'inference'),
('asr.read', 'asr', 'read'),
('tts.inference', 'tts', 'inference'),
('tts.read', 'tts', 'read'),
('nmt.inference', 'nmt', 'inference'),
('nmt.read', 'nmt', 'read'),
('ner.inference', 'ner', 'inference'),
-- Model Management permissions
('model.create', 'models', 'create'),
('model.read', 'models', 'read'),
('model.update', 'models', 'update'),
('model.delete', 'models', 'delete'),
('model.deprecate', 'models', 'deprecate'),
('model.activate', 'models', 'activate'),
-- Service Management permissions
('service.create', 'services', 'create'),
('service.read', 'services', 'read'),
('service.update', 'services', 'update'),
('service.delete', 'services', 'delete'),
('service.publish', 'services', 'publish'),
('service.unpublish', 'services', 'unpublish'),
-- API Key management permissions
('apiKey.create', 'apiKey', 'create'),
('apiKey.read', 'apiKey', 'read'),
('apiKey.update', 'apiKey', 'update'),
('apiKey.delete', 'apiKey', 'delete')
ON CONFLICT (name) DO NOTHING;

-- Assign permissions to ADMIN role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign permissions to USER role + model/service read permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name IN ('users.read', 'users.update', 'configs.read', 'metrics.read', 'alerts.read', 'dashboards.create', 'dashboards.read', 'dashboards.update', 'asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read', 'model.read', 'service.read', 'apiKey.update')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign permissions to GUEST role + model/service read permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'GUEST' 
AND p.name IN ('users.read', 'configs.read', 'metrics.read', 'alerts.read', 'dashboards.read', 'model.read', 'service.read', 'apiKey.update')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign permissions to MODERATOR role + all model/service permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name IN ('users.read', 'users.update', 'configs.read', 'configs.update', 'metrics.read', 'alerts.read', 'alerts.update', 'dashboards.create', 'dashboards.read', 'dashboards.update', 'asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read', 'model.create', 'model.read', 'model.update', 'model.delete', 'model.publish', 'model.unpublish', 'service.create', 'service.read', 'service.update', 'service.delete', 'apiKey.update')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- ============================================================================
-- Create Default Admin User
-- ============================================================================
-- Standard default admin user created during installation/initialization
-- This user has ADMIN role with all permissions
-- 
-- Credentials:
--   Username: admin
--   Email:    admin@ai4i.org
--   Password: Admin@123
--   Role:     ADMIN (all permissions)
--   Status:   ACTIVE
-- ============================================================================

-- Create the default admin user
-- Password hash for "Admin@123" (bcrypt)
INSERT INTO users (email, username, hashed_password, is_active, is_verified, full_name, is_superuser) VALUES
('admin@ai4i.org', 'admin', '$2b$12$4RQ5dBZcbuUGcmtMrySGxOv7Jj4h.v088MTrkTadx4kPfa.GrsaWW', true, true, 'System Administrator', true)
ON CONFLICT (email) DO UPDATE
SET 
    username = EXCLUDED.username,
    hashed_password = EXCLUDED.hashed_password,
    is_active = EXCLUDED.is_active,
    is_verified = EXCLUDED.is_verified,
    full_name = EXCLUDED.full_name,
    is_superuser = EXCLUDED.is_superuser;

-- Assign ADMIN role to the default admin user
-- This ensures the admin user has all permissions through the ADMIN role
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.email = 'admin@ai4i.org' AND u.username = 'admin' AND r.name = 'ADMIN'
ON CONFLICT (user_id, role_id) DO NOTHING;

\c config_db;
-- ============================================================================
-- Setup Complete!
-- ============================================================================
-- All databases, tables, indexes, and seed data have been created.
-- You can now start using the platform.
-- ============================================================================

-- ============================================================================
-- FUTURE IMPLEMENTATION: Additional Service Schemas
-- ============================================================================
-- The following sections contain database schemas for services that are
-- planned but not yet implemented:
--   - Metrics Service (metrics_db)
--   - Telemetry Service (telemetry_db)
--   - Dashboard Service (dashboard_db)
--
-- Note: Alerting Service (alerting_db) has been implemented in STEP 6 above.
--
-- These schemas are commented out to avoid creating unnecessary databases
-- and tables during initial setup. When implementing these services:
--   1. Add database creation blocks in STEP 1 above (following the pattern
--      used for auth_db and config_db)
--   2. Add GRANT statements for the new databases
--   3. Add COMMENT statements for the new databases
--   4. Uncomment the relevant schema section(s) below
--   5. Run this script again or execute the uncommented sections separately
--
-- Example database creation pattern to add in STEP 1:
--   DO $$
--   BEGIN
--       IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metrics_db') THEN
--           CREATE DATABASE metrics_db;
--       END IF;
--   END
--   $$;
-- ============================================================================

-- ============================================================================
-- STEP 6: Metrics Service Schema (metrics_db) - FUTURE IMPLEMENTATION
-- ============================================================================

-- \c metrics_db;

-- -- Metric definitions table
-- CREATE TABLE IF NOT EXISTS metric_definitions (
--     id SERIAL PRIMARY KEY,
--     name VARCHAR(255) UNIQUE NOT NULL,
--     description TEXT,
--     unit VARCHAR(50),
--     metric_type VARCHAR(50) NOT NULL,
--     aggregation_method VARCHAR(50),
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- API metrics table
-- CREATE TABLE IF NOT EXISTS api_metrics (
--     id SERIAL PRIMARY KEY,
--     endpoint VARCHAR(255) NOT NULL,
--     method VARCHAR(10) NOT NULL,
--     status_code INTEGER NOT NULL,
--     response_time DECIMAL(10,3) NOT NULL,
--     request_count INTEGER DEFAULT 1,
--     error_count INTEGER DEFAULT 0,
--     timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     service_name VARCHAR(100) NOT NULL
-- );

-- -- Custom metrics table
-- CREATE TABLE IF NOT EXISTS custom_metrics (
--     id SERIAL PRIMARY KEY,
--     metric_name VARCHAR(255) NOT NULL,
--     value DECIMAL(15,6) NOT NULL,
--     tags JSONB,
--     timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     user_id INTEGER,
--     tenant_id VARCHAR(100)
-- );

-- -- Metric aggregations table
-- CREATE TABLE IF NOT EXISTS metric_aggregations (
--     id SERIAL PRIMARY KEY,
--     metric_name VARCHAR(255) NOT NULL,
--     aggregation_type VARCHAR(50) NOT NULL,
--     value DECIMAL(15,6) NOT NULL,
--     start_time TIMESTAMP WITH TIME ZONE NOT NULL,
--     end_time TIMESTAMP WITH TIME ZONE NOT NULL,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Create indexes for metrics_db
-- CREATE INDEX IF NOT EXISTS idx_api_metrics_timestamp ON api_metrics(timestamp);
-- CREATE INDEX IF NOT EXISTS idx_api_metrics_service_name ON api_metrics(service_name);
-- CREATE INDEX IF NOT EXISTS idx_custom_metrics_metric_name ON custom_metrics(metric_name);
-- CREATE INDEX IF NOT EXISTS idx_custom_metrics_timestamp ON custom_metrics(timestamp);
-- CREATE INDEX IF NOT EXISTS idx_metric_aggregations_metric_name ON metric_aggregations(metric_name);

-- -- ============================================================================
-- -- STEP 7: Telemetry Service Schema (telemetry_db) - FUTURE IMPLEMENTATION
-- -- ============================================================================

-- \c telemetry_db;

-- -- Log metadata table
-- CREATE TABLE IF NOT EXISTS log_metadata (
--     id SERIAL PRIMARY KEY,
--     log_id VARCHAR(255) UNIQUE NOT NULL,
--     service_name VARCHAR(100) NOT NULL,
--     environment VARCHAR(50) NOT NULL,
--     log_level VARCHAR(20) NOT NULL,
--     correlation_id VARCHAR(255),
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Trace metadata table
-- CREATE TABLE IF NOT EXISTS trace_metadata (
--     id SERIAL PRIMARY KEY,
--     trace_id VARCHAR(255) NOT NULL,
--     span_id VARCHAR(255) NOT NULL,
--     parent_span_id VARCHAR(255),
--     service_name VARCHAR(100) NOT NULL,
--     operation_name VARCHAR(255) NOT NULL,
--     duration DECIMAL(10,3) NOT NULL,
--     status VARCHAR(20) NOT NULL,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Event correlations table
-- CREATE TABLE IF NOT EXISTS event_correlations (
--     id SERIAL PRIMARY KEY,
--     correlation_id VARCHAR(255) NOT NULL,
--     event_type VARCHAR(100) NOT NULL,
--     event_count INTEGER DEFAULT 1,
--     first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Data enrichment rules table
-- CREATE TABLE IF NOT EXISTS data_enrichment_rules (
--     id SERIAL PRIMARY KEY,
--     rule_name VARCHAR(255) UNIQUE NOT NULL,
--     source_field VARCHAR(255) NOT NULL,
--     target_field VARCHAR(255) NOT NULL,
--     enrichment_type VARCHAR(50) NOT NULL,
--     configuration JSONB NOT NULL,
--     is_active BOOLEAN DEFAULT true,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Create indexes for telemetry_db
-- CREATE INDEX IF NOT EXISTS idx_log_metadata_log_id ON log_metadata(log_id);
-- CREATE INDEX IF NOT EXISTS idx_log_metadata_service_name ON log_metadata(service_name);
-- CREATE INDEX IF NOT EXISTS idx_trace_metadata_trace_id ON trace_metadata(trace_id);
-- CREATE INDEX IF NOT EXISTS idx_event_correlations_correlation_id ON event_correlations(correlation_id);

-- -- ============================================================================
-- -- STEP 8: Alerting Service Schema (alerting_db) - FUTURE IMPLEMENTATION
-- -- ============================================================================

-- \c alerting_db;

-- -- Alert rules table
-- CREATE TABLE IF NOT EXISTS alert_rules (
--     id SERIAL PRIMARY KEY,
--     name VARCHAR(255) UNIQUE NOT NULL,
--     description TEXT,
--     metric_name VARCHAR(255) NOT NULL,
--     threshold DECIMAL(15,6) NOT NULL,
--     operator VARCHAR(10) NOT NULL,
--     severity VARCHAR(20) NOT NULL,
--     evaluation_window INTEGER DEFAULT 300,
--     notification_channels TEXT[],
--     is_active BOOLEAN DEFAULT true,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     created_by VARCHAR(100)
-- );

-- -- Alerts table
-- CREATE TABLE IF NOT EXISTS alerts (
--     id SERIAL PRIMARY KEY,
--     rule_id INTEGER REFERENCES alert_rules(id) ON DELETE CASCADE,
--     metric_name VARCHAR(255) NOT NULL,
--     current_value DECIMAL(15,6) NOT NULL,
--     threshold DECIMAL(15,6) NOT NULL,
--     severity VARCHAR(20) NOT NULL,
--     status VARCHAR(20) DEFAULT 'firing',
--     fired_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     resolved_at TIMESTAMP WITH TIME ZONE,
--     acknowledged_at TIMESTAMP WITH TIME ZONE,
--     acknowledged_by VARCHAR(100)
-- );

-- -- Notification history table
-- CREATE TABLE IF NOT EXISTS notification_history (
--     id SERIAL PRIMARY KEY,
--     alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
--     channel VARCHAR(50) NOT NULL,
--     recipient VARCHAR(255) NOT NULL,
--     status VARCHAR(20) NOT NULL,
--     sent_at TIMESTAMP WITH TIME ZONE,
--     error_message TEXT
-- );

-- -- Escalation policies table
-- CREATE TABLE IF NOT EXISTS escalation_policies (
--     id SERIAL PRIMARY KEY,
--     name VARCHAR(255) UNIQUE NOT NULL,
--     rules JSONB NOT NULL,
--     schedule JSONB,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Anomaly detection models table
-- CREATE TABLE IF NOT EXISTS anomaly_detection_models (
--     id SERIAL PRIMARY KEY,
--     metric_name VARCHAR(255) NOT NULL,
--     model_type VARCHAR(50) NOT NULL,
--     model_parameters JSONB NOT NULL,
--     training_data_size INTEGER NOT NULL,
--     last_trained_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     accuracy_score DECIMAL(5,4),
--     is_active BOOLEAN DEFAULT true
-- );

-- -- Create indexes for alerting_db
-- CREATE INDEX IF NOT EXISTS idx_alert_rules_name ON alert_rules(name);
-- CREATE INDEX IF NOT EXISTS idx_alerts_rule_id ON alerts(rule_id);
-- CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
-- CREATE INDEX IF NOT EXISTS idx_notification_history_alert_id ON notification_history(alert_id);

-- -- Create triggers for alerting_db
-- CREATE TRIGGER update_alert_rules_updated_at BEFORE UPDATE ON alert_rules
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
-- CREATE TRIGGER update_escalation_policies_updated_at BEFORE UPDATE ON escalation_policies
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- -- ============================================================================
-- -- STEP 9: Dashboard Service Schema (dashboard_db) - FUTURE IMPLEMENTATION
-- -- ============================================================================

-- \c dashboard_db;

-- -- Dashboards table
-- CREATE TABLE IF NOT EXISTS dashboards (
--     id SERIAL PRIMARY KEY,
--     name VARCHAR(255) NOT NULL,
--     description TEXT,
--     layout JSONB NOT NULL,
--     is_public BOOLEAN DEFAULT false,
--     owner_id INTEGER NOT NULL,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Dashboard widgets table
-- CREATE TABLE IF NOT EXISTS dashboard_widgets (
--     id SERIAL PRIMARY KEY,
--     dashboard_id INTEGER REFERENCES dashboards(id) ON DELETE CASCADE,
--     widget_type VARCHAR(100) NOT NULL,
--     configuration JSONB NOT NULL,
--     position JSONB NOT NULL,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Saved queries table
-- CREATE TABLE IF NOT EXISTS saved_queries (
--     id SERIAL PRIMARY KEY,
--     name VARCHAR(255) NOT NULL,
--     query TEXT NOT NULL,
--     parameters JSONB,
--     created_by INTEGER NOT NULL,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Reports table
-- CREATE TABLE IF NOT EXISTS reports (
--     id SERIAL PRIMARY KEY,
--     name VARCHAR(255) NOT NULL,
--     description TEXT,
--     schedule VARCHAR(100),
--     recipients TEXT[],
--     format VARCHAR(20) DEFAULT 'pdf',
--     query_id INTEGER REFERENCES saved_queries(id) ON DELETE SET NULL,
--     last_generated_at TIMESTAMP WITH TIME ZONE,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- User preferences table
-- CREATE TABLE IF NOT EXISTS user_preferences (
--     id SERIAL PRIMARY KEY,
--     user_id INTEGER UNIQUE NOT NULL,
--     preferences JSONB NOT NULL,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- -- Create indexes for dashboard_db
-- CREATE INDEX IF NOT EXISTS idx_dashboards_owner_id ON dashboards(owner_id);
-- CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_dashboard_id ON dashboard_widgets(dashboard_id);
-- CREATE INDEX IF NOT EXISTS idx_saved_queries_created_by ON saved_queries(created_by);
-- CREATE INDEX IF NOT EXISTS idx_reports_query_id ON reports(query_id);
-- CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);

-- -- Create triggers for dashboard_db
-- CREATE TRIGGER update_dashboards_updated_at BEFORE UPDATE ON dashboards
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
-- CREATE TRIGGER update_dashboard_widgets_updated_at BEFORE UPDATE ON dashboard_widgets
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
-- CREATE TRIGGER update_saved_queries_updated_at BEFORE UPDATE ON saved_queries
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
-- CREATE TRIGGER update_reports_updated_at BEFORE UPDATE ON reports
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
-- CREATE TRIGGER update_user_preferences_updated_at BEFORE UPDATE ON user_preferences
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- End of database initialization scripts