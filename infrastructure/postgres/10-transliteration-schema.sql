-- This file creates tables for tracking Transliteration service requests and results.
-- Tables are stored in the auth_db database to maintain referential integrity
-- with users, api_keys, and sessions tables (same pattern as NMT/ASR/TTS/LLM).

\c auth_db;

-- Ensure UUID extension is available (safe to call multiple times)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Transliteration Requests table - tracks transliteration inference requests
CREATE TABLE IF NOT EXISTS transliteration_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    -- Keep session_id for tracking, but do not enforce FK to avoid dependency issues
    session_id INTEGER,
    model_id VARCHAR(100) NOT NULL,
    source_language VARCHAR(10) NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    text_length INTEGER,
    is_sentence_level BOOLEAN NOT NULL DEFAULT TRUE,
    num_suggestions INTEGER DEFAULT 0,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE transliteration_requests IS 'Transliteration requests table - tracks script conversion inference requests';
COMMENT ON COLUMN transliteration_requests.model_id IS 'Identifier for the transliteration model/service used (e.g., ai4bharat/indicxlit)';
COMMENT ON COLUMN transliteration_requests.source_language IS 'Source language code (e.g., en, hi, ta)';
COMMENT ON COLUMN transliteration_requests.target_language IS 'Target language code (e.g., hi, ta)';
COMMENT ON COLUMN transliteration_requests.text_length IS 'Length of input text in characters';
COMMENT ON COLUMN transliteration_requests.is_sentence_level IS 'True for sentence-level transliteration, False for word-level/top-k';
COMMENT ON COLUMN transliteration_requests.num_suggestions IS 'Top-k suggestions requested for word-level transliteration';
COMMENT ON COLUMN transliteration_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN transliteration_requests.status IS 'Current status of the request: processing, completed, or failed';

-- Transliteration Results table - stores transliteration inference results
CREATE TABLE IF NOT EXISTS transliteration_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES transliteration_requests(id) ON DELETE CASCADE,
    transliterated_text JSONB NOT NULL, -- Can be string or list of strings (top-k suggestions)
    source_text TEXT,
    confidence_score FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE transliteration_results IS 'Transliteration results table - stores transliteration inference outputs';
COMMENT ON COLUMN transliteration_results.transliterated_text IS 'Transliterated text, either a single string or an array of strings (JSONB)';
COMMENT ON COLUMN transliteration_results.source_text IS 'Original source text for reference';
COMMENT ON COLUMN transliteration_results.confidence_score IS 'Optional confidence score for the transliteration';

-- Indexes for Transliteration tables
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_user_id ON transliteration_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_api_key_id ON transliteration_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_session_id ON transliteration_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_status ON transliteration_requests(status);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_source_language ON transliteration_requests(source_language);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_target_language ON transliteration_requests(target_language);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_model_id ON transliteration_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_created_at ON transliteration_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_user_created ON transliteration_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_status_created ON transliteration_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_language_pair ON transliteration_requests(source_language, target_language);

CREATE INDEX IF NOT EXISTS idx_transliteration_results_request_id ON transliteration_results(request_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_results_created_at ON transliteration_results(created_at);

-- Trigger to keep updated_at in sync (uses existing update_updated_at_column() from 08-ai-services-schema.sql)
CREATE TRIGGER update_transliteration_requests_updated_at
    BEFORE UPDATE ON transliteration_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


