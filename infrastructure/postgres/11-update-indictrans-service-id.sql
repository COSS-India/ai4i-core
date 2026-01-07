-- ============================================================================
-- Update IndicTrans Service ID in Model Management Database
-- ============================================================================
-- This script updates an existing service entry to use the service_id
-- 'ai4bharat/indictrans-v2-all-gpu'
-- Run this script on the model_management_db database
--
-- Usage:
--   docker compose exec postgres psql -U dhruva_user -d model_management_db -f /docker-entrypoint-initdb.d/11-update-indictrans-service-id.sql
-- ============================================================================

\c model_management_db;

-- ============================================================================
-- Step 1: Find existing IndicTrans service entries
-- ============================================================================
-- Display existing services that might be the IndicTrans service
SELECT 
    service_id,
    name,
    model_id,
    model_version,
    endpoint,
    is_published
FROM services
WHERE service_id LIKE '%indictrans%' 
   OR name LIKE '%IndicTrans%'
   OR name LIKE '%indictrans%'
ORDER BY created_at DESC;

-- ============================================================================
-- Step 2: Update service_id to ai4bharat/indictrans-v2-all-gpu
-- ============================================================================
-- Update the service_id for the existing IndicTrans service
-- This assumes there's an existing service with model_id containing 'indictrans'
-- Adjust the WHERE clause based on the actual existing service_id

-- Option 1: If you know the existing service_id (e.g., 'ai4bharat/indictrans--gpu-t4')
UPDATE services
SET 
    service_id = 'ai4bharat/indictrans-v2-all-gpu',
    updated_at = NOW()
WHERE service_id = 'ai4bharat/indictrans--gpu-t4'
   OR service_id LIKE '%indictrans%'
RETURNING service_id, name, model_id, model_version, endpoint;

-- Option 2: If you want to update based on model_id
-- Uncomment and use this if Option 1 doesn't match:
/*
UPDATE services
SET 
    service_id = 'ai4bharat/indictrans-v2-all-gpu',
    updated_at = NOW()
WHERE model_id LIKE '%indictrans%'
  AND service_id != 'ai4bharat/indictrans-v2-all-gpu'
RETURNING service_id, name, model_id, model_version, endpoint;
*/

-- ============================================================================
-- Verification
-- ============================================================================
-- Verify the update was successful
DO $$
DECLARE
    service_count INTEGER;
    updated_service_id TEXT;
BEGIN
    SELECT COUNT(*), MAX(service_id) INTO service_count, updated_service_id
    FROM services
    WHERE service_id = 'ai4bharat/indictrans-v2-all-gpu';
    
    IF service_count > 0 THEN
        RAISE NOTICE '✓ Service ID updated successfully to: %', updated_service_id;
    ELSE
        RAISE WARNING '✗ Service ID update failed. No service found with ID: ai4bharat/indictrans-v2-all-gpu';
    END IF;
END $$;

-- Display the updated service entry
SELECT 
    'Updated Service Entry' as entry_type,
    service_id,
    name,
    endpoint,
    model_id,
    model_version,
    is_published,
    updated_at
FROM services
WHERE service_id = 'ai4bharat/indictrans-v2-all-gpu';

-- ============================================================================
-- Notes
-- ============================================================================
-- 1. If multiple services match the WHERE clause, all will be updated
-- 2. If no service matches, no rows will be updated (check the SELECT output above)
-- 3. The service_id must be unique, so ensure only one service matches
-- 4. You can manually adjust the WHERE clause based on the existing service_id
-- ============================================================================

