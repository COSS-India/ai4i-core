-- ============================================================================
-- Add IndicTrans v2 All GPU Service to Model Management Database
-- ============================================================================
-- This script adds a new model and service entry for ai4bharat/indictrans-v2-all-gpu
-- Run this script on the model_management_db database
--
-- Usage:
--   docker compose exec postgres psql -U dhruva_user -d model_management_db -f /docker-entrypoint-initdb.d/11-add-indictrans-v2-all-gpu-service.sql
-- ============================================================================

\c model_management_db;

-- ============================================================================
-- Step 0: Ensure unique constraint exists on models table
-- ============================================================================
-- Create the unique constraint if it doesn't exist (from migration 10)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'uq_model_id_version'
    ) THEN
        ALTER TABLE models 
        ADD CONSTRAINT uq_model_id_version UNIQUE (model_id, version);
        RAISE NOTICE 'Created unique constraint uq_model_id_version on models table';
    ELSE
        RAISE NOTICE 'Unique constraint uq_model_id_version already exists';
    END IF;
END $$;

-- ============================================================================
-- Step 1: Insert Model Entry
-- ============================================================================
-- Insert the model entry first (services reference models)
INSERT INTO models (
    id,
    model_id,
    version,
    version_status,
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
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'indictrans-v2-all-gpu',
    '1.0.0',
    'ACTIVE',
    EXTRACT(EPOCH FROM NOW())::BIGINT * 1000,  -- Current timestamp in milliseconds
    NULL,  -- NULL on creation
    'IndicTrans v2 All GPU',
    'Neural Machine Translation model for 22+ Indic languages. GPU-accelerated version supporting bidirectional translation between English and multiple Indic languages.',
    'https://github.com/AI4Bharat/IndicTrans2',
    '{"type": "nmt"}'::jsonb,
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
        {"sourceLanguage": "hi", "targetLanguage": "en"},
        {"sourceLanguage": "ta", "targetLanguage": "en"},
        {"sourceLanguage": "te", "targetLanguage": "en"},
        {"sourceLanguage": "kn", "targetLanguage": "en"},
        {"sourceLanguage": "ml", "targetLanguage": "en"},
        {"sourceLanguage": "bn", "targetLanguage": "en"},
        {"sourceLanguage": "gu", "targetLanguage": "en"},
        {"sourceLanguage": "mr", "targetLanguage": "en"},
        {"sourceLanguage": "pa", "targetLanguage": "en"},
        {"sourceLanguage": "or", "targetLanguage": "en"},
        {"sourceLanguage": "as", "targetLanguage": "en"},
        {"sourceLanguage": "ur", "targetLanguage": "en"}
    ]'::jsonb,
    'MIT',
    '["general", "translation"]'::jsonb,
    '{
        "schema": {
            "modelProcessingType": {"type": "batch"},
            "model_name": "indictrans-v2-all-gpu",
            "request": {
                "input": [{"source": "string"}],
                "config": {
                    "language": {
                        "sourceLanguage": "string",
                        "targetLanguage": "string"
                    }
                }
            },
            "response": {
                "output": [{"target": "string"}]
            }
        }
    }'::jsonb,
    '[]'::jsonb,  -- Empty benchmarks array
    '{
        "name": "AI4Bharat",
        "aboutMe": "AI4Bharat team",
        "team": [
            {
                "name": "AI4Bharat Team",
                "aboutMe": "Open source AI research organization",
                "oauthId": null
            }
        ]
    }'::jsonb,
    NOW(),
    NOW()
)
ON CONFLICT (model_id, version) DO NOTHING;

-- ============================================================================
-- Step 2: Insert Service Entry
-- ============================================================================
-- Insert the service entry that references the model
-- NOTE: Update the endpoint and api_key values as needed for your deployment
INSERT INTO services (
    id,
    service_id,
    name,
    service_description,
    hardware_description,
    published_on,
    model_id,
    model_version,
    endpoint,
    api_key,
    health_status,
    benchmarks,
    is_published,
    published_at,
    unpublished_at,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'ai4bharat/indictrans-v2-all-gpu',
    'IndicTrans v2 All GPU Translation Service',
    'Neural Machine Translation service for translating text between English and 22+ Indic languages. GPU-accelerated version with TensorRT optimization.',
    'GPU instance (T4 or better) with TensorRT optimization',
    EXTRACT(EPOCH FROM NOW())::BIGINT * 1000,  -- Current timestamp in milliseconds
    'indictrans-v2-all-gpu',
    '1.0.0',
    'http://13.200.133.97:8000',  -- Update this with your actual Triton endpoint
    NULL,  -- API key if required, otherwise NULL
    jsonb_build_object('status', 'healthy', 'lastUpdated', NOW()::text),
    '{}'::jsonb,  -- Empty benchmarks object
    true,  -- Published by default
    EXTRACT(EPOCH FROM NOW())::BIGINT * 1000,  -- Published timestamp
    NULL,  -- Not unpublished
    NOW(),
    NOW()
)
ON CONFLICT (service_id) DO UPDATE
SET
    name = EXCLUDED.name,
    service_description = EXCLUDED.service_description,
    hardware_description = EXCLUDED.hardware_description,
    endpoint = EXCLUDED.endpoint,
    api_key = EXCLUDED.api_key,
    health_status = EXCLUDED.health_status,
    model_id = EXCLUDED.model_id,
    model_version = EXCLUDED.model_version,
    updated_at = NOW();

-- ============================================================================
-- Verification
-- ============================================================================
-- Verify the entries were created successfully
DO $$
DECLARE
    model_count INTEGER;
    service_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO model_count
    FROM models
    WHERE model_id = 'indictrans-v2-all-gpu' AND version = '1.0.0';
    
    SELECT COUNT(*) INTO service_count
    FROM services
    WHERE service_id = 'ai4bharat/indictrans-v2-all-gpu';
    
    IF model_count > 0 THEN
        RAISE NOTICE '✓ Model entry created successfully: indictrans-v2-all-gpu v1.0.0';
    ELSE
        RAISE WARNING '✗ Model entry not found. It may already exist or creation failed.';
    END IF;
    
    IF service_count > 0 THEN
        RAISE NOTICE '✓ Service entry created successfully: ai4bharat/indictrans-v2-all-gpu';
    ELSE
        RAISE WARNING '✗ Service entry not found. It may already exist or creation failed.';
    END IF;
END $$;

-- Display the created entries
SELECT 
    'Model Entry' as entry_type,
    model_id,
    version,
    name,
    task->>'type' as task_type
FROM models
WHERE model_id = 'indictrans-v2-all-gpu' AND version = '1.0.0';

SELECT 
    'Service Entry' as entry_type,
    service_id,
    name,
    endpoint,
    model_id,
    model_version,
    is_published
FROM services
WHERE service_id = 'ai4bharat/indictrans-v2-all-gpu';

-- ============================================================================
-- Notes
-- ============================================================================
-- 1. Update the 'endpoint' value in the service entry to match your actual
--    Triton Inference Server endpoint
-- 2. If your Triton server requires an API key, update the 'api_key' field
-- 3. The service is published by default (is_published = true)
-- 4. You can update these values later using the Model Management Service API
-- ============================================================================

