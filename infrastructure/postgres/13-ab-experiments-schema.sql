-- =====================================================
-- A/B Experiments Schema Migration
-- Model Management Service - A/B Testing Feature
-- =====================================================

-- Create enum type for experiment status
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'experiment_status') THEN
        CREATE TYPE experiment_status AS ENUM ('DRAFT', 'RUNNING', 'STOPPED');
    END IF;
END $$;

-- Create ab_experiments table
CREATE TABLE IF NOT EXISTS ab_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    
    -- Task type this experiment applies to (asr, nmt, tts, etc.)
    task_type VARCHAR(100) NOT NULL,
    
    -- Services being compared
    control_service_id VARCHAR(255) NOT NULL,      -- Baseline/current production
    treatment_service_id VARCHAR(255) NOT NULL,    -- New model being tested
    
    -- Traffic split: percentage going to treatment (0-100)
    treatment_percentage INTEGER NOT NULL DEFAULT 50 
        CHECK (treatment_percentage >= 0 AND treatment_percentage <= 100),
    
    -- Experiment status
    status experiment_status NOT NULL DEFAULT 'DRAFT',
    
    -- Audit fields
    created_by VARCHAR(255),
    updated_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,  -- When status changed to RUNNING
    stopped_at TIMESTAMPTZ   -- When status changed to STOPPED
);

-- Partial unique index: only one RUNNING experiment per task_type
-- This ensures only one experiment can be active per task type at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_experiment_per_task 
ON ab_experiments(task_type) 
WHERE status = 'RUNNING';

-- Index for faster lookups by status
CREATE INDEX IF NOT EXISTS idx_ab_experiments_status ON ab_experiments(status);

-- Index for faster lookups by task_type
CREATE INDEX IF NOT EXISTS idx_ab_experiments_task_type ON ab_experiments(task_type);

-- Comment on table
COMMENT ON TABLE ab_experiments IS 'A/B experiments for comparing two model services. Only one experiment can be RUNNING per task_type at a time.';

-- Comments on columns
COMMENT ON COLUMN ab_experiments.control_service_id IS 'Service ID of the control (baseline) model - references services.service_id';
COMMENT ON COLUMN ab_experiments.treatment_service_id IS 'Service ID of the treatment (new) model being tested - references services.service_id';
COMMENT ON COLUMN ab_experiments.treatment_percentage IS 'Percentage of traffic to route to treatment (0-100). E.g., 30 means 30% treatment, 70% control';
COMMENT ON COLUMN ab_experiments.status IS 'DRAFT=not started, RUNNING=actively routing traffic, STOPPED=completed or terminated';

-- Create updated_at trigger function if not exists
CREATE OR REPLACE FUNCTION update_ab_experiments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS trigger_ab_experiments_updated_at ON ab_experiments;
CREATE TRIGGER trigger_ab_experiments_updated_at
    BEFORE UPDATE ON ab_experiments
    FOR EACH ROW
    EXECUTE FUNCTION update_ab_experiments_updated_at();

-- Grant permissions (adjust role name as needed)
-- GRANT ALL ON ab_experiments TO dhruva_user;
