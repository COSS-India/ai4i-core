-- ============================================================================
-- OCR Tables Creation Script
-- ============================================================================
-- This script creates the OCR request and result tables if they don't exist.
-- Run this script to ensure OCR tables are created in the auth_db database.
--
-- Usage:
--   docker compose exec postgres psql -U dhruva_user -d auth_db -f /docker-entrypoint-initdb.d/create-ocr-tables.sql
--   OR
--   psql -U dhruva_user -d auth_db -f create-ocr-tables.sql
-- ============================================================================

\c auth_db;

-- Enable UUID extension for generating UUIDs (if not already enabled)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- OCR Requests table - tracks OCR inference requests
CREATE TABLE IF NOT EXISTS ocr_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) NOT NULL,
    image_count INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE ocr_requests IS 'OCR requests table - tracks OCR inference requests';
COMMENT ON COLUMN ocr_requests.model_id IS 'Identifier for the OCR model used (e.g., surya-ocr)';
COMMENT ON COLUMN ocr_requests.language IS 'Language code for the document text (e.g., en, hi, ta)';
COMMENT ON COLUMN ocr_requests.image_count IS 'Number of images processed in the request';
COMMENT ON COLUMN ocr_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN ocr_requests.status IS 'Current status of the request: processing, completed, or failed';

-- OCR Results table - stores OCR inference results
CREATE TABLE IF NOT EXISTS ocr_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES ocr_requests(id) ON DELETE CASCADE,
    extracted_text TEXT NOT NULL,
    page_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE ocr_results IS 'OCR results table - stores OCR inference results';
COMMENT ON COLUMN ocr_results.extracted_text IS 'The text extracted from the input image(s)';
COMMENT ON COLUMN ocr_results.page_count IS 'Number of pages or images represented by this result row';

-- Indexes for OCR tables
CREATE INDEX IF NOT EXISTS idx_ocr_requests_user_id ON ocr_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_ocr_requests_api_key_id ON ocr_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_ocr_requests_session_id ON ocr_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_ocr_requests_status ON ocr_requests(status);
CREATE INDEX IF NOT EXISTS idx_ocr_requests_language ON ocr_requests(language);
CREATE INDEX IF NOT EXISTS idx_ocr_requests_model_id ON ocr_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_ocr_requests_created_at ON ocr_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_ocr_requests_user_created ON ocr_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ocr_requests_status_created ON ocr_requests(status, created_at);

CREATE INDEX IF NOT EXISTS idx_ocr_results_request_id ON ocr_results(request_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_created_at ON ocr_results(created_at);

-- Create trigger for updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ocr_requests_updated_at
    BEFORE UPDATE ON ocr_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'OCR tables created successfully!';
END $$;

