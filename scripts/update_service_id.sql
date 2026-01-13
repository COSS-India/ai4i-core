-- Script to update service ID from 'asr_am_ensemble' to 'ai4bharat/indictasr'
-- Run this against the model management service database

-- First, check if the service exists
SELECT service_id, name, model_id, model_version, endpoint 
FROM services 
WHERE service_id = 'asr_am_ensemble';

-- Update the service_id
UPDATE services 
SET service_id = 'ai4bharat/indictasr',
    updated_at = NOW()
WHERE service_id = 'asr_am_ensemble';

-- Verify the update
SELECT service_id, name, model_id, model_version, endpoint 
FROM services 
WHERE service_id = 'ai4bharat/indictasr';

-- Note: You may also need to clear Redis cache if caching is enabled
-- The cache key would be based on the old service_id



