-- Telemetry Service Database Schema
-- Connect to telemetry_db and create tables for telemetry data

\c telemetry_db;

-- Log metadata table
CREATE TABLE IF NOT EXISTS log_metadata (
    id SERIAL PRIMARY KEY,
    log_id VARCHAR(255) UNIQUE NOT NULL,
    service_name VARCHAR(100) NOT NULL,
    environment VARCHAR(50) NOT NULL,
    log_level VARCHAR(20) NOT NULL, -- 'DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'
    correlation_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Trace metadata table
CREATE TABLE IF NOT EXISTS trace_metadata (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(255) NOT NULL,
    span_id VARCHAR(255) NOT NULL,
    parent_span_id VARCHAR(255),
    service_name VARCHAR(100) NOT NULL,
    operation_name VARCHAR(255) NOT NULL,
    duration DECIMAL(10,3) NOT NULL, -- in milliseconds
    status VARCHAR(20) NOT NULL, -- 'OK', 'ERROR', 'TIMEOUT'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Event correlations table
CREATE TABLE IF NOT EXISTS event_correlations (
    id SERIAL PRIMARY KEY,
    correlation_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_count INTEGER DEFAULT 1,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Data enrichment rules table
CREATE TABLE IF NOT EXISTS data_enrichment_rules (
    id SERIAL PRIMARY KEY,
    rule_name VARCHAR(255) UNIQUE NOT NULL,
    source_field VARCHAR(255) NOT NULL,
    target_field VARCHAR(255) NOT NULL,
    enrichment_type VARCHAR(50) NOT NULL, -- 'lookup', 'transform', 'add_context'
    configuration JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_log_metadata_log_id ON log_metadata(log_id);
CREATE INDEX IF NOT EXISTS idx_log_metadata_service_name ON log_metadata(service_name);
CREATE INDEX IF NOT EXISTS idx_log_metadata_correlation_id ON log_metadata(correlation_id);
CREATE INDEX IF NOT EXISTS idx_log_metadata_created_at ON log_metadata(created_at);
CREATE INDEX IF NOT EXISTS idx_log_metadata_service_correlation ON log_metadata(service_name, correlation_id);
CREATE INDEX IF NOT EXISTS idx_trace_metadata_trace_id ON trace_metadata(trace_id);
CREATE INDEX IF NOT EXISTS idx_trace_metadata_span_id ON trace_metadata(span_id);
CREATE INDEX IF NOT EXISTS idx_trace_metadata_parent_span_id ON trace_metadata(parent_span_id);
CREATE INDEX IF NOT EXISTS idx_trace_metadata_service_name ON trace_metadata(service_name);
CREATE INDEX IF NOT EXISTS idx_trace_metadata_created_at ON trace_metadata(created_at);
CREATE INDEX IF NOT EXISTS idx_trace_metadata_trace_span ON trace_metadata(trace_id, span_id);
CREATE INDEX IF NOT EXISTS idx_event_correlations_correlation_id ON event_correlations(correlation_id);
CREATE INDEX IF NOT EXISTS idx_event_correlations_event_type ON event_correlations(event_type);
CREATE INDEX IF NOT EXISTS idx_event_correlations_first_seen ON event_correlations(first_seen);
CREATE INDEX IF NOT EXISTS idx_event_correlations_last_seen ON event_correlations(last_seen);
CREATE INDEX IF NOT EXISTS idx_data_enrichment_rules_rule_name ON data_enrichment_rules(rule_name);
CREATE INDEX IF NOT EXISTS idx_data_enrichment_rules_active ON data_enrichment_rules(is_active);

-- Create a function to update last_seen timestamp for event correlations
CREATE OR REPLACE FUNCTION update_event_correlation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    -- Check if correlation_id already exists
    IF EXISTS (SELECT 1 FROM event_correlations WHERE correlation_id = NEW.correlation_id) THEN
        -- Update existing record
        UPDATE event_correlations 
        SET event_count = event_count + 1,
            last_seen = CURRENT_TIMESTAMP
        WHERE correlation_id = NEW.correlation_id;
        RETURN NULL; -- Don't insert new record
    ELSE
        -- Insert new record
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for event correlations
CREATE TRIGGER update_event_correlation_timestamp_trigger
    BEFORE INSERT ON event_correlations
    FOR EACH ROW EXECUTE FUNCTION update_event_correlation_timestamp();

-- Create a function to clean up old telemetry data
CREATE OR REPLACE FUNCTION cleanup_old_telemetry_data(
    log_retention_days integer DEFAULT 30,
    trace_retention_days integer DEFAULT 7
)
RETURNS void AS $$
BEGIN
    -- Delete old log metadata
    DELETE FROM log_metadata 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * log_retention_days;
    
    -- Delete old trace metadata
    DELETE FROM trace_metadata 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * trace_retention_days;
    
    -- Delete old event correlations
    DELETE FROM event_correlations 
    WHERE last_seen < CURRENT_TIMESTAMP - INTERVAL '1 day' * log_retention_days;
END;
$$ LANGUAGE plpgsql;
