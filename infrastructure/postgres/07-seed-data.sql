-- Seed initial data for development and testing
-- This script populates the databases with default data for development

-- Connect to auth_db and insert default roles and permissions
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
-- User management permissions
('users.create', 'users', 'create'),
('users.read', 'users', 'read'),
('users.update', 'users', 'update'),
('users.delete', 'users', 'delete'),
-- Configuration permissions
('configs.create', 'configurations', 'create'),
('configs.read', 'configurations', 'read'),
('configs.update', 'configurations', 'update'),
('configs.delete', 'configurations', 'delete'),
-- Metrics permissions
('metrics.read', 'metrics', 'read'),
('metrics.export', 'metrics', 'export'),
-- Alerts permissions
('alerts.create', 'alerts', 'create'),
('alerts.read', 'alerts', 'read'),
('alerts.update', 'alerts', 'update'),
('alerts.delete', 'alerts', 'delete'),
-- Dashboard permissions
('dashboards.create', 'dashboards', 'create'),
('dashboards.read', 'dashboards', 'read'),
('dashboards.update', 'dashboards', 'update'),
('dashboards.delete', 'dashboards', 'delete')
ON CONFLICT (name) DO NOTHING;

-- Assign permissions to roles
-- ADMIN gets all permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- USER gets read/update on own resources and read on others
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name IN ('users.read', 'users.update', 'configs.read', 'metrics.read', 'alerts.read', 'dashboards.create', 'dashboards.read', 'dashboards.update')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- GUEST gets read-only access
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'GUEST' 
AND p.name IN ('users.read', 'configs.read', 'metrics.read', 'alerts.read', 'dashboards.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- MODERATOR gets read/update on most resources
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name IN ('users.read', 'users.update', 'configs.read', 'configs.update', 'metrics.read', 'alerts.read', 'alerts.update', 'dashboards.create', 'dashboards.read', 'dashboards.update')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Create a default admin user (password: admin123)
-- Note: This is for development only - use a proper password hashing in production
INSERT INTO users (email, username, password_hash, is_active, is_verified) VALUES
('admin@ai4i.com', 'admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/9QZQK2O', true, true)
ON CONFLICT (email) DO NOTHING;

-- Assign ADMIN role to the default admin user
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.email = 'admin@ai4i.com' AND r.name = 'ADMIN'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Connect to config_db and insert sample feature flags
\c config_db;

-- Insert sample feature flags
INSERT INTO feature_flags (name, description, is_enabled, rollout_percentage, environment) VALUES
('new_dashboard_ui', 'Enable new dashboard user interface', false, 0.00, 'development'),
('advanced_analytics', 'Enable advanced analytics features', true, 100.00, 'development'),
('beta_features', 'Enable beta features for testing', false, 25.00, 'development'),
('api_rate_limiting', 'Enable API rate limiting', true, 100.00, 'development'),
('real_time_notifications', 'Enable real-time notifications', true, 50.00, 'development')
ON CONFLICT (name) DO NOTHING;

-- Insert sample configurations
INSERT INTO configurations (key, value, environment, service_name, description) VALUES
('api.timeout', '30', 'development', 'api-gateway-service', 'API request timeout in seconds'),
('cache.ttl', '300', 'development', 'api-gateway-service', 'Cache time-to-live in seconds'),
('rate_limit.requests_per_minute', '100', 'development', 'api-gateway-service', 'Rate limit per minute'),
('jwt.expiry_minutes', '15', 'development', 'auth-service', 'JWT token expiry in minutes'),
('jwt.refresh_expiry_days', '7', 'development', 'auth-service', 'JWT refresh token expiry in days'),
('metrics.retention_days', '90', 'development', 'metrics-service', 'Metrics retention period in days'),
('alerts.cooldown_minutes', '15', 'development', 'alerting-service', 'Alert cooldown period in minutes'),
('dashboard.refresh_interval', '30', 'development', 'dashboard-service', 'Dashboard refresh interval in seconds')
ON CONFLICT (key, environment, service_name) DO NOTHING;

-- Insert sample service registry entries
INSERT INTO service_registry (service_name, service_url, health_check_url, status, metadata) VALUES
('api-gateway-service', 'http://api-gateway-service:8080', 'http://api-gateway-service:8080/health', 'healthy', '{"version": "1.0.0", "environment": "development"}'),
('auth-service', 'http://auth-service:8081', 'http://auth-service:8081/health', 'healthy', '{"version": "1.0.0", "environment": "development"}'),
('config-service', 'http://config-service:8082', 'http://config-service:8082/health', 'healthy', '{"version": "1.0.0", "environment": "development"}'),
('metrics-service', 'http://metrics-service:8083', 'http://metrics-service:8083/health', 'healthy', '{"version": "1.0.0", "environment": "development"}'),
('telemetry-service', 'http://telemetry-service:8084', 'http://telemetry-service:8084/health', 'healthy', '{"version": "1.0.0", "environment": "development"}'),
('alerting-service', 'http://alerting-service:8085', 'http://alerting-service:8085/health', 'healthy', '{"version": "1.0.0", "environment": "development"}'),
('dashboard-service', 'http://dashboard-service:8086', 'http://dashboard-service:8086/health', 'healthy', '{"version": "1.0.0", "environment": "development"}')
ON CONFLICT (service_name) DO NOTHING;

-- AI Services Seed Data
-- Sample data for testing ASR, TTS, and NMT service tables
\c auth_db;

-- Insert AI service permissions
INSERT INTO permissions (name, resource, action) VALUES
-- ASR permissions
('asr.inference', 'asr', 'inference'),
('asr.read', 'asr', 'read'),
-- TTS permissions
('tts.inference', 'tts', 'inference'),
('tts.read', 'tts', 'read'),
-- NMT permissions
('nmt.inference', 'nmt', 'inference'),
('nmt.read', 'nmt', 'read')
ON CONFLICT (name) DO NOTHING;

-- Assign AI service permissions to roles
-- ADMIN gets all AI service permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'ADMIN' 
AND p.name IN ('asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- USER gets inference and read permissions for AI services
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'USER' 
AND p.name IN ('asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- MODERATOR gets all AI service permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'MODERATOR' 
AND p.name IN ('asr.inference', 'asr.read', 'tts.inference', 'tts.read', 'nmt.inference', 'nmt.read')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Sample ASR Requests
INSERT INTO asr_requests (user_id, model_id, language, audio_duration, processing_time, status, error_message) VALUES
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'vakyansh-asr-en', 'en', 5.5, 0.8, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'vakyansh-asr-hi', 'hi', 12.3, 1.5, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'conformer-asr-multilingual', 'ta', 30.0, 3.2, 'processing', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'vakyansh-asr-en', 'en', 8.7, 1.1, 'failed', 'Audio format not supported'),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'conformer-asr-multilingual', 'te', 15.2, 2.1, 'completed', NULL)
ON CONFLICT DO NOTHING;

-- Sample ASR Results
INSERT INTO asr_results (request_id, transcript, confidence_score, word_timestamps, language_detected, audio_format, sample_rate) VALUES
((SELECT id FROM asr_requests WHERE model_id = 'vakyansh-asr-en' AND language = 'en' LIMIT 1), 
 'Hello, this is a test transcription', 0.95, 
 '{"words": [{"word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.98}, {"word": "this", "start": 0.6, "end": 0.8, "confidence": 0.94}]}'::jsonb, 
 'en', 'WAV', 16000),
((SELECT id FROM asr_requests WHERE model_id = 'vakyansh-asr-hi' AND language = 'hi' LIMIT 1), 
 'नमस्ते, यह एक परीक्षण है', 0.87, 
 '{"words": [{"word": "नमस्ते", "start": 0.0, "end": 1.2, "confidence": 0.89}, {"word": "यह", "start": 1.3, "end": 1.6, "confidence": 0.85}]}'::jsonb, 
 'hi', 'MP3', 22050),
((SELECT id FROM asr_requests WHERE model_id = 'conformer-asr-multilingual' AND language = 'te' LIMIT 1), 
 'హలో, ఇది ఒక పరీక్ష', 0.92, 
 '{"words": [{"word": "హలో", "start": 0.0, "end": 0.8, "confidence": 0.94}, {"word": "ఇది", "start": 0.9, "end": 1.1, "confidence": 0.90}]}'::jsonb, 
 'te', 'FLAC', 44100)
ON CONFLICT DO NOTHING;

-- Sample TTS Requests
INSERT INTO tts_requests (user_id, model_id, voice_id, language, text_length, processing_time, status, error_message) VALUES
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'indic-tts-en', 'female-1', 'en', 50, 1.2, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'indic-tts-hi', 'male-1', 'hi', 120, 2.5, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'glow-tts-multilingual', 'female-2', 'ta', 200, 4.0, 'processing', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'indic-tts-en', 'male-2', 'en', 75, 1.8, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'glow-tts-multilingual', 'custom-voice', 'te', 150, 3.2, 'completed', NULL)
ON CONFLICT DO NOTHING;

-- Sample TTS Results
INSERT INTO tts_results (request_id, audio_file_path, audio_duration, audio_format, sample_rate, bit_rate, file_size) VALUES
((SELECT id FROM tts_requests WHERE model_id = 'indic-tts-en' AND voice_id = 'female-1' LIMIT 1), 
 '/data/audio/tts_output_001.wav', 3.5, 'WAV', 22050, 128, 156000),
((SELECT id FROM tts_requests WHERE model_id = 'indic-tts-hi' AND voice_id = 'male-1' LIMIT 1), 
 '/data/audio/tts_output_002.mp3', 7.2, 'MP3', 44100, 192, 320000),
((SELECT id FROM tts_requests WHERE model_id = 'indic-tts-en' AND voice_id = 'male-2' LIMIT 1), 
 '/data/audio/tts_output_003.wav', 5.1, 'WAV', 22050, 128, 204000),
((SELECT id FROM tts_requests WHERE model_id = 'glow-tts-multilingual' AND voice_id = 'custom-voice' LIMIT 1), 
 '/data/audio/tts_output_004.ogg', 12.0, 'OGG', 44100, 256, 540000)
ON CONFLICT DO NOTHING;

-- Sample NMT Requests
INSERT INTO nmt_requests (user_id, model_id, source_language, target_language, text_length, processing_time, status, error_message) VALUES
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'indictrans-v2', 'en', 'hi', 45, 0.5, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'nmt-en-hi', 'hi', 'en', 100, 1.0, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'nmt-multilingual', 'en', 'ta', 250, 2.0, 'processing', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'indictrans-v2', 'ta', 'en', 80, 1.2, 'completed', NULL),
((SELECT id FROM users WHERE email = 'admin@ai4i.com'), 'nmt-multilingual', 'te', 'en', 120, 1.5, 'completed', NULL)
ON CONFLICT DO NOTHING;

-- Sample NMT Results
INSERT INTO nmt_results (request_id, translated_text, confidence_score, source_text, language_detected, word_alignments) VALUES
((SELECT id FROM nmt_requests WHERE model_id = 'indictrans-v2' AND source_language = 'en' AND target_language = 'hi' LIMIT 1), 
 'नमस्ते दुनिया', 0.94, 'Hello world', 'en', 
 '{"alignments": [{"source": "Hello", "target": "नमस्ते", "score": 0.96}, {"source": "world", "target": "दुनिया", "score": 0.92}]}'::jsonb),
((SELECT id FROM nmt_requests WHERE model_id = 'nmt-en-hi' AND source_language = 'hi' AND target_language = 'en' LIMIT 1), 
 'Good morning', 0.89, 'शुभ प्रभात', 'hi', 
 '{"alignments": [{"source": "शुभ", "target": "Good", "score": 0.91}, {"source": "प्रभात", "target": "morning", "score": 0.87}]}'::jsonb),
((SELECT id FROM nmt_requests WHERE model_id = 'indictrans-v2' AND source_language = 'ta' AND target_language = 'en' LIMIT 1), 
 'How are you?', 0.91, 'நீங்கள் எப்படி இருக்கிறீர்கள்?', 'ta', 
 '{"alignments": [{"source": "நீங்கள்", "target": "you", "score": 0.93}, {"source": "எப்படி", "target": "how", "score": 0.89}, {"source": "இருக்கிறீர்கள்", "target": "are", "score": 0.90}]}'::jsonb),
((SELECT id FROM nmt_requests WHERE model_id = 'nmt-multilingual' AND source_language = 'te' AND target_language = 'en' LIMIT 1), 
 'Thank you very much', 0.88, 'చాలా ధన్యవాదాలు', 'te', 
 '{"alignments": [{"source": "చాలా", "target": "very much", "score": 0.90}, {"source": "ధన్యవాదాలు", "target": "thank you", "score": 0.86}]}'::jsonb)
ON CONFLICT DO NOTHING;

-- Add comments indicating this is for development only
COMMENT ON TABLE users IS 'Users table - contains default admin user for development (password: admin123)';
COMMENT ON TABLE feature_flags IS 'Feature flags table - contains sample feature flags for development';
COMMENT ON TABLE configurations IS 'Configurations table - contains sample configurations for development';
COMMENT ON TABLE service_registry IS 'Service registry table - contains sample service entries for development';
COMMENT ON TABLE asr_requests IS 'ASR requests table - contains sample requests for development';
COMMENT ON TABLE asr_results IS 'ASR results table - contains sample results for development';
COMMENT ON TABLE tts_requests IS 'TTS requests table - contains sample requests for development';
COMMENT ON TABLE tts_results IS 'TTS results table - contains sample results for development';
COMMENT ON TABLE nmt_requests IS 'NMT requests table - contains sample requests for development';
COMMENT ON TABLE nmt_results IS 'NMT results table - contains sample results for development';
