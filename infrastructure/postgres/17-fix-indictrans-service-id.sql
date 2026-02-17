-- Migration: Fix existing ai4bharat/indictrans-v2-all-gpu service
-- This script updates the service_id from human-readable format to hash format
-- and ensures the model_id matches an existing model

\c model_management_db;

-- ============================================================================
-- Step 1: Check current state
-- ============================================================================
SELECT 
    'Current service state' AS info,
    id,
    service_id AS current_service_id,
    name AS service_name,
    model_id AS current_model_id,
    model_version,
    endpoint
FROM services 
WHERE service_id = 'ai4bharat/indictrans-v2-all-gpu'
   OR name LIKE '%indictrans%'
LIMIT 5;

-- ============================================================================
-- Step 2: Find or create the model
-- ============================================================================
DO $$
DECLARE
    v_model_name TEXT := 'ai4bharat/indictrans-v2';
    v_model_version TEXT := '1.0.0';
    v_model_id VARCHAR(32);
    v_current_epoch BIGINT;
    v_existing_model_id VARCHAR(32);
BEGIN
    -- Get current epoch in milliseconds
    v_current_epoch := EXTRACT(EPOCH FROM NOW())::BIGINT * 1000;
    
    -- Generate expected model_id hash
    v_model_id := generate_model_id(v_model_name, v_model_version);
    
    -- Check if model exists
    SELECT model_id INTO v_existing_model_id
    FROM models 
    WHERE name = v_model_name AND version = v_model_version
    LIMIT 1;
    
    IF v_existing_model_id IS NULL THEN
        -- Model doesn't exist, create it
        INSERT INTO models (
            model_id,
            version,
            name,
            description,
            task,
            languages,
            domain,
            license,
            inference_endpoint,
            submitter,
            submitted_on,
            version_status
        ) VALUES (
            v_model_id,
            v_model_version,
            v_model_name,
            'IndicTrans v2 - Neural Machine Translation model supporting multiple Indic languages',
            '{"type": "translation", "subtype": "nmt"}'::jsonb,
            '["hi", "en", "ta", "te", "kn", "ml", "mr", "gu", "pa", "bn", "or", "as", "ne"]'::jsonb,
            '["general", "news", "literary"]'::jsonb,
            'MIT',
            '{"type": "triton", "base_url": "http://triton-inference-server:8000", "model_name": "nmt"}'::jsonb,
            '{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{"name": "Admin", "role": "Maintainer"}]}'::jsonb,
            v_current_epoch,
            'ACTIVE'
        ) ON CONFLICT (name, version) DO NOTHING;
        
        RAISE NOTICE 'Created model: % (version: %, model_id: %)', v_model_name, v_model_version, v_model_id;
    ELSE
        RAISE NOTICE 'Model already exists: % (version: %, model_id: %)', v_model_name, v_model_version, v_existing_model_id;
        v_model_id := v_existing_model_id;
    END IF;
END $$;

-- ============================================================================
-- Step 3: Update the service with correct service_id hash and model_id
-- ============================================================================
DO $$
DECLARE
    v_model_name TEXT := 'ai4bharat/indictrans-v2';
    v_model_version TEXT := '1.0.0';
    v_service_name TEXT := 'all-gpu';  -- Extract from "ai4bharat/indictrans-v2-all-gpu"
    v_old_service_id TEXT := 'ai4bharat/indictrans-v2-all-gpu';
    v_new_service_id VARCHAR(32);
    v_model_id VARCHAR(32);
    v_service_uuid UUID;
BEGIN
    -- Generate the correct service_id hash
    v_new_service_id := generate_service_id(v_model_name, v_model_version, v_service_name);
    
    -- Get the model_id
    SELECT model_id INTO v_model_id
    FROM models 
    WHERE name = v_model_name AND version = v_model_version
    LIMIT 1;
    
    IF v_model_id IS NULL THEN
        RAISE EXCEPTION 'Model % (version: %) not found. Please create it first.', v_model_name, v_model_version;
    END IF;
    
    -- Find the service by old service_id
    SELECT id INTO v_service_uuid
    FROM services 
    WHERE service_id = v_old_service_id
    LIMIT 1;
    
    IF v_service_uuid IS NULL THEN
        RAISE EXCEPTION 'Service with service_id % not found.', v_old_service_id;
    END IF;
    
    -- Check if new service_id already exists (hash collision check)
    IF EXISTS (SELECT 1 FROM services WHERE service_id = v_new_service_id AND id != v_service_uuid) THEN
        RAISE EXCEPTION 'Service with new service_id % already exists. This is a hash collision!', v_new_service_id;
    END IF;
    
    -- Update the service
    UPDATE services
    SET 
        service_id = v_new_service_id,
        model_id = v_model_id,
        model_version = v_model_version,
        name = v_service_name,  -- Update name to just "all-gpu"
        updated_at = CURRENT_TIMESTAMP
    WHERE id = v_service_uuid;
    
    RAISE NOTICE 'Updated service:';
    RAISE NOTICE '  Old service_id: %', v_old_service_id;
    RAISE NOTICE '  New service_id: %', v_new_service_id;
    RAISE NOTICE '  Model_id: %', v_model_id;
    RAISE NOTICE '  Service name: %', v_service_name;
END $$;

-- ============================================================================
-- Step 4: Verification
-- ============================================================================
SELECT 'Verification - Updated service:' AS info;

SELECT 
    id,
    service_id,
    name AS service_name,
    model_id,
    model_version,
    endpoint,
    is_published
FROM services 
WHERE service_id = generate_service_id('ai4bharat/indictrans-v2', '1.0.0', 'all-gpu');

-- Show the model
SELECT 'Verification - Model:' AS info;

SELECT 
    model_id,
    name,
    version,
    version_status
FROM models 
WHERE name = 'ai4bharat/indictrans-v2' AND version = '1.0.0';

-- Show hash comparison
SELECT 
    'Hash verification' AS info,
    'ai4bharat/indictrans-v2-all-gpu' AS old_service_id,
    generate_service_id('ai4bharat/indictrans-v2', '1.0.0', 'all-gpu') AS expected_hash,
    (SELECT service_id FROM services WHERE name = 'all-gpu' AND model_id = generate_model_id('ai4bharat/indictrans-v2', '1.0.0') LIMIT 1) AS actual_service_id,
    CASE 
        WHEN generate_service_id('ai4bharat/indictrans-v2', '1.0.0', 'all-gpu') = 
             (SELECT service_id FROM services WHERE name = 'all-gpu' AND model_id = generate_model_id('ai4bharat/indictrans-v2', '1.0.0') LIMIT 1)
        THEN '✓ Match - Service ID is now a hash'
        ELSE '✗ Mismatch - Check the update'
    END AS verification;
