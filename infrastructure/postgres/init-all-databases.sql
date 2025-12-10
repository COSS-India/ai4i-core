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

-- Create unleash database
-- (Error can be ignored if database already exists)
CREATE DATABASE unleash
    WITH ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.utf8'
    LC_CTYPE = 'en_US.utf8'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1;

-- Grant all privileges on each database to the configured PostgreSQL user
GRANT ALL PRIVILEGES ON DATABASE auth_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE config_db TO dhruva_user;
GRANT ALL PRIVILEGES ON DATABASE unleash TO dhruva_user;

-- Add comments documenting which service uses each database
COMMENT ON DATABASE auth_db IS 'Authentication & Authorization Service database';
COMMENT ON DATABASE config_db IS 'Configuration Management Service database';
COMMENT ON DATABASE unleash IS 'Unleash feature flag management database';

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
    language VARCHAR(10) DEFAULT 'en'
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
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP WITH TIME ZONE
);

-- Create sequence for user_sessions if it doesn't exist
CREATE SEQUENCE IF NOT EXISTS sessions_id_seq;

-- User sessions table (renamed from sessions)
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER DEFAULT nextval('sessions_id_seq') NOT NULL,
    user_id INTEGER,
    session_token VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    refresh_token VARCHAR(255),
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

-- Add comments to document the changes
COMMENT ON COLUMN api_keys.key_name IS 'Name/label for the API key';
COMMENT ON COLUMN api_keys.permissions IS 'Array of permission strings for the API key';
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
-- STEP 4: Seed Data
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
('nmt.read', 'nmt', 'read')
ON CONFLICT (name) DO NOTHING;

-- Assign permissions to ADMIN role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign permissions to USER role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name IN ('users.read', 'users.update', 'configs.read', 'metrics.read', 'alerts.read', 'dashboards.create', 'dashboards.read', 'dashboards.update', 'asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign permissions to GUEST role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'GUEST' 
AND p.name IN ('users.read', 'configs.read', 'metrics.read', 'alerts.read', 'dashboards.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign permissions to MODERATOR role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name IN ('users.read', 'users.update', 'configs.read', 'configs.update', 'metrics.read', 'alerts.read', 'alerts.update', 'dashboards.create', 'dashboards.read', 'dashboards.update', 'asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Create default admin user (password: admin123)
INSERT INTO users (email, username, hashed_password, is_active, is_verified) VALUES
('admin@ai4i.com', 'admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/9QZQK2O', true, true)
ON CONFLICT (email) DO NOTHING;

-- Assign ADMIN role to default admin user
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.email = 'admin@ai4i.com' AND r.name = 'ADMIN'
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
--   - Alerting Service (alerting_db)
--   - Dashboard Service (dashboard_db)
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
-- STEP 4: Metrics Service Schema (metrics_db)
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
-- -- STEP 5: Telemetry Service Schema (telemetry_db)
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
-- -- STEP 6: Alerting Service Schema (alerting_db)
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
-- -- STEP 7: Dashboard Service Schema (dashboard_db)
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