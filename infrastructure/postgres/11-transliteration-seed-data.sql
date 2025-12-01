-- Transliteration Service Seed Data
-- This script populates the databases with transliteration service configuration and sample data

-- ============================================================
-- AUTH_DB: Add transliteration permissions and sample requests
-- ============================================================
\c auth_db;

-- Insert transliteration service permissions
INSERT INTO permissions (name, resource, action) VALUES
('transliteration.inference', 'transliteration', 'inference'),
('transliteration.read', 'transliteration', 'read'),
('transliteration.manage', 'transliteration', 'manage')
ON CONFLICT (name) DO NOTHING;

-- Assign transliteration permissions to roles
-- ADMIN gets all transliteration permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN' 
AND p.name IN ('transliteration.inference', 'transliteration.read', 'transliteration.manage')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- USER gets inference and read permissions for transliteration service
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name IN ('transliteration.inference', 'transliteration.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- MODERATOR gets all transliteration permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name IN ('transliteration.inference', 'transliteration.read', 'transliteration.manage')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Sample Transliteration Requests
INSERT INTO transliteration_requests (
    user_id, 
    model_id, 
    source_language, 
    target_language, 
    text_length, 
    is_sentence_level, 
    num_suggestions, 
    processing_time, 
    status, 
    error_message
) VALUES
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-xlit', 'en', 'hi', 15, false, 3, 0.3, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-xlit', 'en', 'ta', 20, true, 0, 0.5, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-xlit', 'en', 'te', 25, false, 5, 0.4, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-xlit', 'en', 'kn', 18, true, 0, 0.6, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@dhruva-platform.com'), 'ai4bharat-indic-xlit', 'en', 'ml', 30, false, 3, 0.7, 'processing', NULL)
ON CONFLICT DO NOTHING;

-- Sample Transliteration Results
INSERT INTO transliteration_results (
    request_id, 
    source_text, 
    transliterated_text, 
    confidence_score
) VALUES
(
    (SELECT id FROM transliteration_requests WHERE model_id = 'ai4bharat-indic-xlit' AND source_language = 'en' AND target_language = 'hi' LIMIT 1),
    'namaste',
    '["नमस्ते", "नमस्ते", "नमस्कार"]'::jsonb,
    0.96
),
(
    (SELECT id FROM transliteration_requests WHERE model_id = 'ai4bharat-indic-xlit' AND source_language = 'en' AND target_language = 'ta' LIMIT 1),
    'vanakkam',
    '["வணக்கம்"]'::jsonb,
    0.94
),
(
    (SELECT id FROM transliteration_requests WHERE model_id = 'ai4bharat-indic-xlit' AND source_language = 'en' AND target_language = 'te' LIMIT 1),
    'namaskaram',
    '["నమస్కారం", "నమస్కరం", "నమస్కారము", "నమస్తే", "నమస్కర"]'::jsonb,
    0.92
),
(
    (SELECT id FROM transliteration_requests WHERE model_id = 'ai4bharat-indic-xlit' AND source_language = 'en' AND target_language = 'kn' LIMIT 1),
    'namaskara',
    '["ನಮಸ್ಕಾರ"]'::jsonb,
    0.93
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- CONFIG_DB: Add transliteration service configuration
-- ============================================================
\c config_db;

-- Insert transliteration service configurations
INSERT INTO configurations (key, value, environment, service_name) VALUES
('triton.endpoint', '65.1.35.3:8200', 'development', 'transliteration-service'),
('triton.api_key', 'your_api_key', 'development', 'transliteration-service'),
('triton.model_name', 'ai4bharat-indic-xlit', 'development', 'transliteration-service'),
('triton.timeout', '20', 'development', 'transliteration-service'),
('max_batch_size', '100', 'development', 'transliteration-service'),
('max_text_length', '10000', 'development', 'transliteration-service'),
('default_source_language', 'en', 'development', 'transliteration-service'),
('enable_text_normalization', 'true', 'development', 'transliteration-service'),
('rate_limit.requests_per_minute', '60', 'development', 'transliteration-service'),
('rate_limit.requests_per_hour', '1000', 'development', 'transliteration-service')
ON CONFLICT (key, environment, service_name) DO NOTHING;

-- Insert transliteration service registry entry
INSERT INTO service_registry (service_name, service_url, health_check_url, status, service_metadata) VALUES
('transliteration-service', 
 'http://transliteration-service:8090', 
 'http://transliteration-service:8090/api/v1/transliteration/health', 
 'healthy', 
 '{
   "version": "1.0.0",
   "environment": "development",
   "serviceId": "ai4bharat-transliteration",
   "modelId": "ai4bharat-indic-xlit",
   "task": {"type": "transliteration"},
   "endpoint": "65.1.35.3:8200",
   "api_key": "your_api_key",
   "description": "Indic Transliteration Model supporting 24+ Indian languages",
   "supportedLanguages": [
     "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
     "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi",
     "mai", "brx", "mni", "sat", "gom"
   ],
   "supportedScripts": [
     "Latn", "Deva", "Arab", "Taml", "Telu", "Knda", "Mlym", 
     "Beng", "Gujr", "Guru", "Orya"
   ],
   "languagePairs": [
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "hi", "targetScriptCode": "Deva"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "bn", "targetScriptCode": "Beng"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "gu", "targetScriptCode": "Gujr"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "pa", "targetScriptCode": "Guru"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "or", "targetScriptCode": "Orya"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "mr", "targetScriptCode": "Deva"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "kn", "targetScriptCode": "Knda"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "te", "targetScriptCode": "Telu"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "ml", "targetScriptCode": "Mlym"},
     {"sourceLanguage": "en", "sourceScriptCode": "Latn", "targetLanguage": "ta", "targetScriptCode": "Taml"}
   ],
   "inferenceEndpoint": {
     "schema": {
       "request": {
         "inputs": [
           {"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1]},
           {"name": "SOURCE_LANGUAGE", "datatype": "BYTES", "shape": [1, 1]},
           {"name": "TARGET_LANGUAGE", "datatype": "BYTES", "shape": [1, 1]}
         ],
         "outputs": [
           {"name": "OUTPUT_TEXT", "datatype": "BYTES", "shape": [1, 1]}
         ]
       }
     }
   },
   "benchmarks": {
     "avgLatency": "0.5s",
     "throughput": "100 req/s",
     "accuracy": "94%"
   },
   "license": "MIT",
   "domain": ["general", "transliteration"],
   "submitter": {
     "name": "AI4Bharat",
     "aboutMe": "AI4Bharat is a community for open source AI for Indian languages."
   }
 }'::jsonb
)
ON CONFLICT (service_name) DO NOTHING;

-- Insert feature flags for transliteration service
INSERT INTO feature_flags (name, description, is_enabled, rollout_percentage, environment) VALUES
('transliteration_word_level', 'Enable word-level transliteration with multiple suggestions', true, '100', 'development'),
('transliteration_sentence_level', 'Enable sentence-level transliteration', true, '100', 'development'),
('transliteration_auto_detect', 'Enable automatic language detection for transliteration', false, '0', 'development'),
('transliteration_batch_processing', 'Enable batch processing for transliteration requests', true, '100', 'development')
ON CONFLICT (name, environment) DO NOTHING;

-- Add comments
\c auth_db;
COMMENT ON TABLE transliteration_requests IS 'Transliteration requests table - contains sample requests for development';
COMMENT ON TABLE transliteration_results IS 'Transliteration results table - contains sample results for development';

\c config_db;
COMMENT ON TABLE service_registry IS 'Service registry includes transliteration-service configuration and metadata';

