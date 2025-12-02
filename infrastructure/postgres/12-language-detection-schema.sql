-- This file creates tables for tracking Language Detection (IndicLID) service requests and results.
-- All tables are stored in the auth_db database to maintain referential integrity.

\c auth_db;

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Language Detection Requests table - tracks language detection inference requests
CREATE TABLE IF NOT EXISTS language_detection_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER,  -- No FK to avoid dependency
    model_id VARCHAR(100) NOT NULL,
    text_length INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE language_detection_requests IS 'Language detection requests table - tracks text language identification inference requests';
COMMENT ON COLUMN language_detection_requests.model_id IS 'Identifier for the language detection model used (e.g., ai4bharat/indiclid, indiclid)';
COMMENT ON COLUMN language_detection_requests.text_length IS 'Total length of input text in characters';
COMMENT ON COLUMN language_detection_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN language_detection_requests.status IS 'Current status of the request: processing, completed, or failed';

-- Language Detection Results table - stores language detection inference results
CREATE TABLE IF NOT EXISTS language_detection_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES language_detection_requests(id) ON DELETE CASCADE,
    source_text TEXT NOT NULL,
    detected_language VARCHAR(10) NOT NULL,  -- ISO 639-3 code (e.g., 'hin', 'eng', 'tam')
    detected_script VARCHAR(10) NOT NULL,    -- ISO 15924 code (e.g., 'Deva', 'Latn', 'Taml')
    confidence_score FLOAT CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    language_name VARCHAR(100),              -- Full language name (e.g., 'Hindi', 'English')
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE language_detection_results IS 'Language detection results table - stores text language identification inference results';
COMMENT ON COLUMN language_detection_results.source_text IS 'The input text for language detection';
COMMENT ON COLUMN language_detection_results.detected_language IS 'ISO 639-3 language code (e.g., hin for Hindi, eng for English)';
COMMENT ON COLUMN language_detection_results.detected_script IS 'ISO 15924 script code (e.g., Deva for Devanagari, Latn for Latin)';
COMMENT ON COLUMN language_detection_results.confidence_score IS 'Confidence score for the language detection (0.0 to 1.0)';
COMMENT ON COLUMN language_detection_results.language_name IS 'Full language name (e.g., Hindi, English, Tamil)';

-- Indexes for Language Detection tables
CREATE INDEX IF NOT EXISTS idx_language_detection_requests_user_id ON language_detection_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_language_detection_requests_api_key_id ON language_detection_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_language_detection_requests_session_id ON language_detection_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_language_detection_requests_status ON language_detection_requests(status);
CREATE INDEX IF NOT EXISTS idx_language_detection_requests_model_id ON language_detection_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_language_detection_requests_created_at ON language_detection_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_language_detection_requests_user_created ON language_detection_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_language_detection_requests_status_created ON language_detection_requests(status, created_at);

CREATE INDEX IF NOT EXISTS idx_language_detection_results_request_id ON language_detection_results(request_id);
CREATE INDEX IF NOT EXISTS idx_language_detection_results_detected_language ON language_detection_results(detected_language);
CREATE INDEX IF NOT EXISTS idx_language_detection_results_detected_script ON language_detection_results(detected_script);
CREATE INDEX IF NOT EXISTS idx_language_detection_results_created_at ON language_detection_results(created_at);

-- Create trigger for updated_at column (reuse existing function)
CREATE TRIGGER update_language_detection_requests_updated_at
    BEFORE UPDATE ON language_detection_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

