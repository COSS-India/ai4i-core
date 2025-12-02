-- Language Detection Service Seed Data
-- This script populates the databases with language detection service configuration and sample data

-- ============================================================
-- AUTH_DB: Add language detection permissions and sample requests
-- ============================================================
\c auth_db;

-- Insert language detection service permissions
INSERT INTO permissions (name, resource, action) VALUES
('language-detection.inference', 'language-detection', 'inference'),
('language-detection.read', 'language-detection', 'read'),
('language-detection.manage', 'language-detection', 'manage')
ON CONFLICT (name) DO NOTHING;

-- Assign language detection permissions to roles
-- ADMIN gets all language detection permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN' 
AND p.name IN ('language-detection.inference', 'language-detection.read', 'language-detection.manage')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- USER gets inference and read permissions for language detection service
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name IN ('language-detection.inference', 'language-detection.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- MODERATOR gets all language detection permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name IN ('language-detection.inference', 'language-detection.read', 'language-detection.manage')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Sample Language Detection Requests
INSERT INTO language_detection_requests (
    user_id, 
    model_id, 
    text_length, 
    processing_time, 
    status, 
    error_message
) VALUES
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-lid', 15, 0.2, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-lid', 25, 0.3, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-lid', 30, 0.4, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-lid', 20, 0.3, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-lid', 18, 0.2, 'processing', NULL)
ON CONFLICT DO NOTHING;

-- Sample Language Detection Results
INSERT INTO language_detection_results (
    request_id, 
    source_text, 
    detected_language, 
    detected_script, 
    confidence_score,
    language_name
) VALUES
(
    (SELECT id FROM language_detection_requests WHERE model_id = 'ai4bharat-indic-lid' AND text_length = 15 LIMIT 1),
    'नमस्ते दुनिया',
    'hin',
    'Deva',
    0.98,
    'Hindi'
),
(
    (SELECT id FROM language_detection_requests WHERE model_id = 'ai4bharat-indic-lid' AND text_length = 25 LIMIT 1),
    'Hello world',
    'eng',
    'Latn',
    0.99,
    'English'
),
(
    (SELECT id FROM language_detection_requests WHERE model_id = 'ai4bharat-indic-lid' AND text_length = 30 LIMIT 1),
    'வணக்கம் உலகம்',
    'tam',
    'Taml',
    0.97,
    'Tamil'
),
(
    (SELECT id FROM language_detection_requests WHERE model_id = 'ai4bharat-indic-lid' AND text_length = 20 LIMIT 1),
    'నమస్కారం ప్రపంచం',
    'tel',
    'Telu',
    0.96,
    'Telugu'
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- CONFIG_DB: Add language detection service configuration
-- ============================================================
\c config_db;

-- Insert language detection service configurations
INSERT INTO configurations (key, value, environment, service_name) VALUES
('triton.endpoint', '65.1.35.3:8000', 'development', 'language-detection-service'),
('triton.api_key', 'your_api_key', 'development', 'language-detection-service'),
('triton.model_name', 'indiclid', 'development', 'language-detection-service'),
('triton.timeout', '20', 'development', 'language-detection-service'),
('max_batch_size', '100', 'development', 'language-detection-service'),
('max_text_length', '10000', 'development', 'language-detection-service'),
('enable_text_normalization', 'true', 'development', 'language-detection-service'),
('rate_limit.requests_per_minute', '100', 'development', 'language-detection-service'),
('rate_limit.requests_per_hour', '2000', 'development', 'language-detection-service')
ON CONFLICT (key, environment, service_name) DO NOTHING;

-- Insert language detection service registry entry
INSERT INTO service_registry (service_name, service_url, health_check_url, status, service_metadata) VALUES
('language-detection-service', 
 'http://language-detection-service:8090', 
 'http://language-detection-service:8090/api/v1/language-detection/health', 
 'healthy', 
 '{
   "version": "1.0.0",
   "environment": "development",
   "serviceId": "ai4bharat-indiclid",
   "modelId": "ai4bharat-indic-lid",
   "task": {"type": "txt-lang-detection"},
   "endpoint": "65.1.35.3:8000",
   "api_key": "your_api_key",
   "description": "AI4Bharat Indic Language Identification Model supporting 22+ Indian languages and English in both native and Latin scripts",
   "supportedLanguages": [
     {"code": "as", "name": "Assamese", "scripts": ["Beng", "Latn"]},
     {"code": "bn", "name": "Bengali", "scripts": ["Beng", "Latn"]},
     {"code": "brx", "name": "Bodo", "scripts": ["Deva", "Latn"]},
     {"code": "doi", "name": "Dogri", "scripts": ["Deva", "Latn"]},
     {"code": "en", "name": "English", "scripts": ["Latn"]},
     {"code": "gu", "name": "Gujarati", "scripts": ["Gujr", "Latn"]},
     {"code": "hi", "name": "Hindi", "scripts": ["Deva", "Latn"]},
     {"code": "kn", "name": "Kannada", "scripts": ["Knda", "Latn"]},
     {"code": "ks", "name": "Kashmiri", "scripts": ["Arab", "Deva", "Latn"]},
     {"code": "kok", "name": "Konkani", "scripts": ["Deva", "Latn"]},
     {"code": "mai", "name": "Maithili", "scripts": ["Deva", "Latn"]},
     {"code": "ml", "name": "Malayalam", "scripts": ["Mlym", "Latn"]},
     {"code": "mni", "name": "Manipuri", "scripts": ["Beng", "Mtei", "Latn"]},
     {"code": "mr", "name": "Marathi", "scripts": ["Deva", "Latn"]},
     {"code": "ne", "name": "Nepali", "scripts": ["Deva", "Latn"]},
     {"code": "or", "name": "Odia", "scripts": ["Orya", "Latn"]},
     {"code": "pa", "name": "Punjabi", "scripts": ["Guru", "Latn"]},
     {"code": "sa", "name": "Sanskrit", "scripts": ["Deva", "Latn"]},
     {"code": "sat", "name": "Santali", "scripts": ["Olck"]},
     {"code": "sd", "name": "Sindhi", "scripts": ["Arab", "Latn"]},
     {"code": "ta", "name": "Tamil", "scripts": ["Taml", "Latn"]},
     {"code": "te", "name": "Telugu", "scripts": ["Telu", "Latn"]},
     {"code": "ur", "name": "Urdu", "scripts": ["Arab", "Latn"]},
     {"code": "other", "name": "Other", "scripts": ["Latn"]}
   ],
   "inferenceEndpoint": {
     "schema": {
       "request": {
         "inputs": [
           {"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1]}
         ],
         "outputs": [
           {"name": "OUTPUT_TEXT", "datatype": "BYTES", "shape": [1, 1]}
         ]
       }
     }
   },
   "benchmarks": {
     "avgLatency": "0.2s",
     "throughput": "200 req/s",
     "accuracy": "98%"
   },
   "license": "MIT",
   "domain": ["general", "language-identification"],
   "refUrl": "https://github.com/AI4Bharat/IndicLID",
   "submitter": {
     "name": "AI4Bharat",
     "aboutMe": "AI4Bharat is a community for open source AI for Indian languages."
   }
 }'::jsonb
)
ON CONFLICT (service_name) DO NOTHING;

-- Insert feature flags for language detection service
INSERT INTO feature_flags (name, description, is_enabled, rollout_percentage, environment) VALUES
('language_detection_multi_script', 'Enable multi-script language detection for the same language', true, '100', 'development'),
('language_detection_batch_processing', 'Enable batch processing for language detection requests', true, '100', 'development'),
('language_detection_cache', 'Enable caching of language detection results', false, '0', 'development')
ON CONFLICT (name, environment) DO NOTHING;

-- Add comments
\c auth_db;
COMMENT ON TABLE language_detection_requests IS 'Language detection requests table - contains sample requests for development';
COMMENT ON TABLE language_detection_results IS 'Language detection results table - contains sample results for development';

\c config_db;
COMMENT ON TABLE service_registry IS 'Service registry includes language-detection-service configuration and metadata';

