-- Transliteration Service Seed Data
-- This script inserts sample transliteration models and services into the model management database
-- Run this after the model management service database is initialized

-- Connect to model management database
\c model_management_db;

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Insert AI4Bharat IndicXlit Model
INSERT INTO models (
    id,
    model_id,
    version,
    submitted_on,
    updated_on,
    name,
    description,
    ref_url,
    task,
    languages,
    license,
    domain,
    inference_endpoint,
    benchmarks,
    submitter,
    is_published,
    published_at
) VALUES (
    gen_random_uuid(),
    'ai4bharat/indicxlit',
    '1.0.0',
    EXTRACT(EPOCH FROM NOW())::bigint,
    EXTRACT(EPOCH FROM NOW())::bigint,
    'IndicXlit - Indic Language Transliteration Model',
    'State-of-the-art transliteration model for converting text between English and 20+ Indic languages. Supports both word-level and sentence-level transliteration with top-k suggestions.',
    'https://github.com/AI4Bharat/IndicXlit',
    '{"type": "transliteration"}'::jsonb,
    '[
        {"sourceLanguage": "en", "targetLanguage": "hi"},
        {"sourceLanguage": "en", "targetLanguage": "ta"},
        {"sourceLanguage": "en", "targetLanguage": "te"},
        {"sourceLanguage": "en", "targetLanguage": "kn"},
        {"sourceLanguage": "en", "targetLanguage": "ml"},
        {"sourceLanguage": "en", "targetLanguage": "bn"},
        {"sourceLanguage": "en", "targetLanguage": "gu"},
        {"sourceLanguage": "en", "targetLanguage": "mr"},
        {"sourceLanguage": "en", "targetLanguage": "pa"},
        {"sourceLanguage": "en", "targetLanguage": "or"},
        {"sourceLanguage": "en", "targetLanguage": "as"},
        {"sourceLanguage": "en", "targetLanguage": "ur"},
        {"sourceLanguage": "en", "targetLanguage": "sa"},
        {"sourceLanguage": "en", "targetLanguage": "ks"},
        {"sourceLanguage": "en", "targetLanguage": "ne"},
        {"sourceLanguage": "en", "targetLanguage": "sd"},
        {"sourceLanguage": "en", "targetLanguage": "kok"},
        {"sourceLanguage": "en", "targetLanguage": "doi"},
        {"sourceLanguage": "en", "targetLanguage": "mai"},
        {"sourceLanguage": "en", "targetLanguage": "brx"},
        {"sourceLanguage": "en", "targetLanguage": "mni"},
        {"sourceLanguage": "en", "targetLanguage": "sat"},
        {"sourceLanguage": "en", "targetLanguage": "gom"}
    ]'::jsonb,
    'MIT',
    '["general", "indic-languages"]'::jsonb,
    '{"modelName": "transliteration", "format": "triton"}'::jsonb,
    '[]'::jsonb,
    '{"name": "AI4Bharat", "organization": "IIT Madras", "contact": "ai4bharat@cse.iitm.ac.in"}'::jsonb,
    true,
    EXTRACT(EPOCH FROM NOW())::bigint
) ON CONFLICT (model_id) DO UPDATE SET
    updated_on = EXTRACT(EPOCH FROM NOW())::bigint,
    description = EXCLUDED.description,
    is_published = true,
    published_at = EXTRACT(EPOCH FROM NOW())::bigint;

-- Insert Transliteration Service for AI4Bharat IndicXlit
INSERT INTO services (
    id,
    service_id,
    name,
    service_description,
    hardware_description,
    published_on,
    model_id,
    endpoint,
    api_key,
    health_status,
    benchmarks,
    is_published,
    published_at
) VALUES (
    gen_random_uuid(),
    'ai4bharat/indicxlit',
    'IndicXlit Production Service',
    'Production transliteration service for AI4Bharat IndicXlit model. Supports word-level and sentence-level transliteration for 20+ Indic languages.',
    'Triton Inference Server on GPU: NVIDIA Tesla V100, 16GB VRAM',
    EXTRACT(EPOCH FROM NOW())::bigint,
    'ai4bharat/indicxlit',
    '65.1.35.3:8200',
    'your_api_key',
    jsonb_build_object('status', 'healthy', 'lastUpdated', NOW()::text, 'uptime', '99.9%'),
    '[]'::jsonb,
    true,
    EXTRACT(EPOCH FROM NOW())::bigint
) ON CONFLICT (service_id) DO UPDATE SET
    service_description = EXCLUDED.service_description,
    endpoint = EXCLUDED.endpoint,
    health_status = EXCLUDED.health_status,
    is_published = true,
    published_at = EXTRACT(EPOCH FROM NOW())::bigint;

-- Insert alias service for backwards compatibility
INSERT INTO services (
    id,
    service_id,
    name,
    service_description,
    hardware_description,
    published_on,
    model_id,
    endpoint,
    api_key,
    health_status,
    benchmarks,
    is_published,
    published_at
) VALUES (
    gen_random_uuid(),
    'indicxlit',
    'IndicXlit Service (Alias)',
    'Alias for AI4Bharat IndicXlit service for backwards compatibility.',
    'Triton Inference Server on GPU: NVIDIA Tesla V100, 16GB VRAM',
    EXTRACT(EPOCH FROM NOW())::bigint,
    'ai4bharat/indicxlit',
    '65.1.35.3:8200',
    'your_api_key',
    jsonb_build_object('status', 'healthy', 'lastUpdated', NOW()::text),
    '[]'::jsonb,
    true,
    EXTRACT(EPOCH FROM NOW())::bigint
) ON CONFLICT (service_id) DO UPDATE SET
    endpoint = EXCLUDED.endpoint,
    health_status = EXCLUDED.health_status,
    is_published = true,
    published_at = EXTRACT(EPOCH FROM NOW())::bigint;

-- Insert another alias for ai4bharat-transliteration
INSERT INTO services (
    id,
    service_id,
    name,
    service_description,
    hardware_description,
    published_on,
    model_id,
    endpoint,
    api_key,
    health_status,
    benchmarks,
    is_published,
    published_at
) VALUES (
    gen_random_uuid(),
    'ai4bharat-transliteration',
    'AI4Bharat Transliteration Service (Alias)',
    'Alias for AI4Bharat IndicXlit service for backwards compatibility.',
    'Triton Inference Server on GPU: NVIDIA Tesla V100, 16GB VRAM',
    EXTRACT(EPOCH FROM NOW())::bigint,
    'ai4bharat/indicxlit',
    '65.1.35.3:8200',
    'your_api_key',
    jsonb_build_object('status', 'healthy', 'lastUpdated', NOW()::text),
    '[]'::jsonb,
    true,
    EXTRACT(EPOCH FROM NOW())::bigint
) ON CONFLICT (service_id) DO UPDATE SET
    endpoint = EXCLUDED.endpoint,
    health_status = EXCLUDED.health_status,
    is_published = true,
    published_at = EXTRACT(EPOCH FROM NOW())::bigint;

-- Verify the data was inserted
SELECT 
    model_id, 
    name, 
    version,
    (task->>'type') as task_type,
    is_published
FROM models 
WHERE model_id LIKE '%transliteration%' OR model_id LIKE '%indicxlit%';

SELECT 
    service_id, 
    name, 
    model_id,
    endpoint,
    is_published
FROM services 
WHERE model_id LIKE '%transliteration%' OR model_id LIKE '%indicxlit%';

-- Success message
\echo '✅ Transliteration service seed data inserted successfully!'
\echo ''
\echo 'Available services:'
\echo '  - ai4bharat/indicxlit (primary)'
\echo '  - indicxlit (alias)'
\echo '  - ai4bharat-transliteration (alias)'
\echo ''
\echo 'All services point to endpoint: 65.1.35.3:8200'
\echo 'Triton model name: transliteration'

