-- AI Services Database Schema
-- This file creates tables for tracking ASR (Automatic Speech Recognition),
-- TTS (Text-to-Speech), and NMT (Neural Machine Translation) service requests and results.
-- All tables are stored in the auth_db database to maintain referential integrity
-- with users, api_keys, and sessions tables.

\c auth_db;

-- Enable UUID extension for generating UUIDs
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ASR (Automatic Speech Recognition) Tables

-- ASR Requests table - tracks ASR inference requests
CREATE TABLE IF NOT EXISTS asr_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) NOT NULL,
    audio_duration FLOAT,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE asr_requests IS 'ASR requests table - tracks speech recognition inference requests';
COMMENT ON COLUMN asr_requests.model_id IS 'Identifier for the ASR model used (e.g., vakyansh-asr-en, conformer-asr-multilingual)';
COMMENT ON COLUMN asr_requests.language IS 'Language code for the audio (e.g., en, hi, ta, te)';
COMMENT ON COLUMN asr_requests.audio_duration IS 'Duration of input audio in seconds';
COMMENT ON COLUMN asr_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN asr_requests.status IS 'Current status of the request: processing, completed, or failed';

-- ASR Results table - stores ASR inference results
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

COMMENT ON TABLE asr_results IS 'ASR results table - stores speech recognition inference results';
COMMENT ON COLUMN asr_results.transcript IS 'The transcribed text from the audio';
COMMENT ON COLUMN asr_results.confidence_score IS 'Overall confidence score for the transcription (0.0 to 1.0)';
COMMENT ON COLUMN asr_results.word_timestamps IS 'Word-level timestamps and confidence scores in JSONB format';
COMMENT ON COLUMN asr_results.language_detected IS 'Detected language if different from requested language';
COMMENT ON COLUMN asr_results.audio_format IS 'Format of input audio (WAV, MP3, FLAC, etc.)';
COMMENT ON COLUMN asr_results.sample_rate IS 'Audio sample rate in Hz';

-- TTS (Text-to-Speech) Tables

-- TTS Requests table - tracks TTS inference requests
CREATE TABLE IF NOT EXISTS tts_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
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

COMMENT ON TABLE tts_requests IS 'TTS requests table - tracks text-to-speech inference requests';
COMMENT ON COLUMN tts_requests.model_id IS 'Identifier for the TTS model used (e.g., indic-tts-en, glow-tts-multilingual)';
COMMENT ON COLUMN tts_requests.voice_id IS 'Voice identifier (e.g., female-1, male-2, custom-voice)';
COMMENT ON COLUMN tts_requests.language IS 'Language code for the text (e.g., en, hi, ta)';
COMMENT ON COLUMN tts_requests.text_length IS 'Length of input text in characters';
COMMENT ON COLUMN tts_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN tts_requests.status IS 'Current status of the request: processing, completed, or failed';

-- TTS Results table - stores TTS inference results
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

COMMENT ON TABLE tts_results IS 'TTS results table - stores text-to-speech inference results';
COMMENT ON COLUMN tts_results.audio_file_path IS 'Path to the generated audio file';
COMMENT ON COLUMN tts_results.audio_duration IS 'Duration of generated audio in seconds';
COMMENT ON COLUMN tts_results.audio_format IS 'Format of output audio (WAV, MP3, OGG, etc.)';
COMMENT ON COLUMN tts_results.sample_rate IS 'Audio sample rate in Hz';
COMMENT ON COLUMN tts_results.bit_rate IS 'Audio bit rate in kbps';
COMMENT ON COLUMN tts_results.file_size IS 'Size of audio file in bytes';

-- LLM (Large Language Model) Tables

-- LLM Requests table - tracks LLM inference requests
CREATE TABLE IF NOT EXISTS llm_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
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

COMMENT ON TABLE llm_requests IS 'LLM requests table - tracks large language model inference requests';
COMMENT ON COLUMN llm_requests.model_id IS 'Identifier for the LLM model used (e.g., llm, ai4bharat/llm)';
COMMENT ON COLUMN llm_requests.input_language IS 'Input language code (e.g., en, hi, ta)';
COMMENT ON COLUMN llm_requests.output_language IS 'Output language code (e.g., en, hi, ta)';
COMMENT ON COLUMN llm_requests.text_length IS 'Length of input text in characters';
COMMENT ON COLUMN llm_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN llm_requests.status IS 'Current status of the request: processing, completed, or failed';

-- LLM Results table - stores LLM inference results
CREATE TABLE IF NOT EXISTS llm_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES llm_requests(id) ON DELETE CASCADE,
    output_text TEXT NOT NULL,
    source_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE llm_results IS 'LLM results table - stores large language model inference results';
COMMENT ON COLUMN llm_results.output_text IS 'The processed/translated/generated text output';
COMMENT ON COLUMN llm_results.source_text IS 'Original source text for reference';

-- NMT (Neural Machine Translation) Tables

-- NMT Requests table - tracks NMT inference requests
CREATE TABLE IF NOT EXISTS nmt_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
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

COMMENT ON TABLE nmt_requests IS 'NMT requests table - tracks neural machine translation inference requests';
COMMENT ON COLUMN nmt_requests.model_id IS 'Identifier for the NMT model used (e.g., indictrans-v2, nmt-en-hi)';
COMMENT ON COLUMN nmt_requests.source_language IS 'Source language code (e.g., en, hi, ta)';
COMMENT ON COLUMN nmt_requests.target_language IS 'Target language code (e.g., en, hi, ta)';
COMMENT ON COLUMN nmt_requests.text_length IS 'Length of input text in characters';
COMMENT ON COLUMN nmt_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN nmt_requests.status IS 'Current status of the request: processing, completed, or failed';

-- NMT Results table - stores NMT inference results
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

COMMENT ON TABLE nmt_results IS 'NMT results table - stores neural machine translation inference results';
COMMENT ON COLUMN nmt_results.translated_text IS 'The translated text';
COMMENT ON COLUMN nmt_results.confidence_score IS 'Overall confidence score for the translation (0.0 to 1.0)';
COMMENT ON COLUMN nmt_results.source_text IS 'Original source text for reference';
COMMENT ON COLUMN nmt_results.language_detected IS 'Detected source language if different from requested';
COMMENT ON COLUMN nmt_results.word_alignments IS 'Word-level alignment information in JSONB format';

-- OCR (Optical Character Recognition) Tables

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

-- Indexes for ASR tables
CREATE INDEX IF NOT EXISTS idx_asr_requests_user_id ON asr_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_asr_requests_api_key_id ON asr_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_asr_requests_session_id ON asr_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_asr_requests_status ON asr_requests(status);
CREATE INDEX IF NOT EXISTS idx_asr_requests_language ON asr_requests(language);
CREATE INDEX IF NOT EXISTS idx_asr_requests_model_id ON asr_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_asr_requests_created_at ON asr_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_asr_requests_user_created ON asr_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_asr_requests_status_created ON asr_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_asr_requests_model_language ON asr_requests(model_id, language);

CREATE INDEX IF NOT EXISTS idx_asr_results_request_id ON asr_results(request_id);
CREATE INDEX IF NOT EXISTS idx_asr_results_created_at ON asr_results(created_at);

-- Indexes for TTS tables
CREATE INDEX IF NOT EXISTS idx_tts_requests_user_id ON tts_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_api_key_id ON tts_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_session_id ON tts_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_status ON tts_requests(status);
CREATE INDEX IF NOT EXISTS idx_tts_requests_language ON tts_requests(language);
CREATE INDEX IF NOT EXISTS idx_tts_requests_model_id ON tts_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_voice_id ON tts_requests(voice_id);
CREATE INDEX IF NOT EXISTS idx_tts_requests_created_at ON tts_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_tts_requests_user_created ON tts_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tts_requests_status_created ON tts_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_tts_requests_model_language ON tts_requests(model_id, language);

CREATE INDEX IF NOT EXISTS idx_tts_results_request_id ON tts_results(request_id);
CREATE INDEX IF NOT EXISTS idx_tts_results_created_at ON tts_results(created_at);

-- Indexes for NMT tables
CREATE INDEX IF NOT EXISTS idx_nmt_requests_user_id ON nmt_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_api_key_id ON nmt_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_session_id ON nmt_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_status ON nmt_requests(status);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_source_language ON nmt_requests(source_language);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_target_language ON nmt_requests(target_language);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_model_id ON nmt_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_created_at ON nmt_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_user_created ON nmt_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_status_created ON nmt_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_nmt_requests_language_pair ON nmt_requests(source_language, target_language);

CREATE INDEX IF NOT EXISTS idx_nmt_results_request_id ON nmt_results(request_id);
CREATE INDEX IF NOT EXISTS idx_nmt_results_created_at ON nmt_results(created_at);

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

-- Indexes for LLM tables
CREATE INDEX IF NOT EXISTS idx_llm_requests_user_id ON llm_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_api_key_id ON llm_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_session_id ON llm_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_status ON llm_requests(status);
CREATE INDEX IF NOT EXISTS idx_llm_requests_input_language ON llm_requests(input_language);
CREATE INDEX IF NOT EXISTS idx_llm_requests_output_language ON llm_requests(output_language);
CREATE INDEX IF NOT EXISTS idx_llm_requests_model_id ON llm_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_created_at ON llm_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_requests_user_created ON llm_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_llm_requests_status_created ON llm_requests(status, created_at);

CREATE INDEX IF NOT EXISTS idx_llm_results_request_id ON llm_results(request_id);
CREATE INDEX IF NOT EXISTS idx_llm_results_created_at ON llm_results(created_at);

-- Language Detection Tables

-- Language Detection Requests table - tracks language detection inference requests
CREATE TABLE IF NOT EXISTS language_detection_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER,
    model_id VARCHAR(100) NOT NULL,
    text_length INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE language_detection_requests IS 'Language detection requests table - tracks language detection inference requests';
COMMENT ON COLUMN language_detection_requests.model_id IS 'Identifier for the language detection model used (e.g., ai4bharat/indiclid, indiclid)';
COMMENT ON COLUMN language_detection_requests.text_length IS 'Length of input text in characters';
COMMENT ON COLUMN language_detection_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN language_detection_requests.status IS 'Current status of the request: processing, completed, or failed';

-- Language Detection Results table - stores language detection inference results
CREATE TABLE IF NOT EXISTS language_detection_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES language_detection_requests(id) ON DELETE CASCADE,
    source_text TEXT NOT NULL,
    detected_language VARCHAR(10) NOT NULL,
    detected_script VARCHAR(10) NOT NULL,
    confidence_score FLOAT NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    language_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE language_detection_results IS 'Language detection results table - stores language detection inference results';
COMMENT ON COLUMN language_detection_results.source_text IS 'The input text that was analyzed';
COMMENT ON COLUMN language_detection_results.detected_language IS 'ISO 639-3 language code (e.g., hin, eng, tam)';
COMMENT ON COLUMN language_detection_results.detected_script IS 'ISO 15924 script code (e.g., Deva, Latn, Taml)';
COMMENT ON COLUMN language_detection_results.confidence_score IS 'Confidence score for the detection (0.0 to 1.0)';
COMMENT ON COLUMN language_detection_results.language_name IS 'Full language name (e.g., Hindi, English)';

-- Transliteration Tables

-- Transliteration Requests table - tracks transliteration inference requests
CREATE TABLE IF NOT EXISTS transliteration_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    source_language VARCHAR(10) NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    text_length INTEGER,
    is_sentence_level BOOLEAN DEFAULT true,
    num_suggestions INTEGER DEFAULT 0,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE transliteration_requests IS 'Transliteration requests table - tracks transliteration inference requests';
COMMENT ON COLUMN transliteration_requests.model_id IS 'Identifier for the transliteration model used';
COMMENT ON COLUMN transliteration_requests.source_language IS 'Source language code (e.g., en, hi, ta)';
COMMENT ON COLUMN transliteration_requests.target_language IS 'Target language code (e.g., en, hi, ta)';
COMMENT ON COLUMN transliteration_requests.text_length IS 'Length of input text in characters';
COMMENT ON COLUMN transliteration_requests.is_sentence_level IS 'Whether transliteration is at sentence level (true) or word level (false)';
COMMENT ON COLUMN transliteration_requests.num_suggestions IS 'Number of transliteration suggestions requested';
COMMENT ON COLUMN transliteration_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN transliteration_requests.status IS 'Current status of the request: processing, completed, or failed';

-- Transliteration Results table - stores transliteration inference results
CREATE TABLE IF NOT EXISTS transliteration_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES transliteration_requests(id) ON DELETE CASCADE,
    transliterated_text JSONB NOT NULL,
    source_text TEXT,
    confidence_score FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE transliteration_results IS 'Transliteration results table - stores transliteration inference results';
COMMENT ON COLUMN transliteration_results.transliterated_text IS 'The transliterated text (can be string or list of strings for top-k)';
COMMENT ON COLUMN transliteration_results.source_text IS 'Original source text for reference';
COMMENT ON COLUMN transliteration_results.confidence_score IS 'Confidence score for the transliteration (optional)';

-- NER (Named Entity Recognition) Tables

-- NER Requests table - tracks NER inference requests
CREATE TABLE IF NOT EXISTS ner_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    model_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) NOT NULL,
    text_length INTEGER,
    processing_time FLOAT,
    status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE ner_requests IS 'NER requests table - tracks named entity recognition inference requests';
COMMENT ON COLUMN ner_requests.model_id IS 'Identifier for the NER model used';
COMMENT ON COLUMN ner_requests.language IS 'Language code for the input text (e.g., en, hi, ta)';
COMMENT ON COLUMN ner_requests.text_length IS 'Length of input text in characters';
COMMENT ON COLUMN ner_requests.processing_time IS 'Time taken to process the request in seconds';
COMMENT ON COLUMN ner_requests.status IS 'Current status of the request: processing, completed, or failed';

-- NER Results table - stores NER inference results
CREATE TABLE IF NOT EXISTS ner_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES ner_requests(id) ON DELETE CASCADE,
    entities JSONB NOT NULL,
    source_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE ner_results IS 'NER results table - stores named entity recognition inference results';
COMMENT ON COLUMN ner_results.entities IS 'JSON structure containing extracted entities, labels, and offsets';
COMMENT ON COLUMN ner_results.source_text IS 'Original source text for reference';

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
CREATE INDEX IF NOT EXISTS idx_language_detection_results_created_at ON language_detection_results(created_at);
CREATE INDEX IF NOT EXISTS idx_language_detection_results_detected_language ON language_detection_results(detected_language);

-- Indexes for Transliteration tables
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_user_id ON transliteration_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_api_key_id ON transliteration_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_session_id ON transliteration_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_status ON transliteration_requests(status);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_model_id ON transliteration_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_source_language ON transliteration_requests(source_language);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_target_language ON transliteration_requests(target_language);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_created_at ON transliteration_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_user_created ON transliteration_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_status_created ON transliteration_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_transliteration_requests_language_pair ON transliteration_requests(source_language, target_language);

CREATE INDEX IF NOT EXISTS idx_transliteration_results_request_id ON transliteration_results(request_id);
CREATE INDEX IF NOT EXISTS idx_transliteration_results_created_at ON transliteration_results(created_at);

-- Indexes for NER tables
CREATE INDEX IF NOT EXISTS idx_ner_requests_user_id ON ner_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_ner_requests_api_key_id ON ner_requests(api_key_id);
CREATE INDEX IF NOT EXISTS idx_ner_requests_session_id ON ner_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_ner_requests_status ON ner_requests(status);
CREATE INDEX IF NOT EXISTS idx_ner_requests_language ON ner_requests(language);
CREATE INDEX IF NOT EXISTS idx_ner_requests_model_id ON ner_requests(model_id);
CREATE INDEX IF NOT EXISTS idx_ner_requests_created_at ON ner_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_ner_requests_user_created ON ner_requests(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ner_requests_status_created ON ner_requests(status, created_at);

CREATE INDEX IF NOT EXISTS idx_ner_results_request_id ON ner_results(request_id);
CREATE INDEX IF NOT EXISTS idx_ner_results_created_at ON ner_results(created_at);

-- Check if update_updated_at_column function exists, create if not
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns
CREATE TRIGGER update_asr_requests_updated_at
    BEFORE UPDATE ON asr_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tts_requests_updated_at
    BEFORE UPDATE ON tts_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_nmt_requests_updated_at
    BEFORE UPDATE ON nmt_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_llm_requests_updated_at
    BEFORE UPDATE ON llm_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_language_detection_requests_updated_at
    BEFORE UPDATE ON language_detection_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_transliteration_requests_updated_at
    BEFORE UPDATE ON transliteration_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ocr_requests_updated_at
    BEFORE UPDATE ON ocr_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ner_requests_updated_at
    BEFORE UPDATE ON ner_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Utility function for cleaning up old AI service data
CREATE OR REPLACE FUNCTION cleanup_old_ai_service_data(retention_days INTEGER DEFAULT 90)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    -- Delete old ASR data
    DELETE FROM asr_results 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    DELETE FROM asr_requests 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    -- Delete old TTS data
    DELETE FROM tts_results 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    DELETE FROM tts_requests 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    -- Delete old NMT data
    DELETE FROM nmt_results 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    DELETE FROM nmt_requests 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    -- Delete old LLM data
    DELETE FROM llm_results 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    DELETE FROM llm_requests 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    -- Delete old Language Detection data
    DELETE FROM language_detection_results 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    DELETE FROM language_detection_requests 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    -- Delete old Transliteration data
    DELETE FROM transliteration_results 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    DELETE FROM transliteration_requests 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;

    -- Delete old OCR data
    DELETE FROM ocr_results
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;

    DELETE FROM ocr_requests
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;

    -- Delete old NER data
    DELETE FROM ner_results
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;

    DELETE FROM ner_requests
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    RAISE NOTICE 'Cleaned up AI service data older than % days', retention_days;
END;
$$;
