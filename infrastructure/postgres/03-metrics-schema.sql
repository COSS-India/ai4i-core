-- Metrics Service Database Schema
-- Connect to metrics_db and create tables for metrics collection

\c metrics_db;

-- Metric definitions table
CREATE TABLE IF NOT EXISTS metric_definitions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    unit VARCHAR(50),
    metric_type VARCHAR(50) NOT NULL, -- 'counter', 'gauge', 'histogram', 'summary'
    aggregation_method VARCHAR(50), -- 'sum', 'avg', 'min', 'max', 'count'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- API metrics table for time-series data
CREATE TABLE IF NOT EXISTS api_metrics (
    id SERIAL PRIMARY KEY,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER NOT NULL,
    response_time DECIMAL(10,3) NOT NULL, -- in milliseconds
    request_count INTEGER DEFAULT 1,
    error_count INTEGER DEFAULT 0,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    service_name VARCHAR(100) NOT NULL
);

-- Custom metrics table
CREATE TABLE IF NOT EXISTS custom_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(255) NOT NULL,
    value DECIMAL(15,6) NOT NULL,
    tags JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    tenant_id VARCHAR(100)
);

-- Metric aggregations table for pre-computed aggregations
CREATE TABLE IF NOT EXISTS metric_aggregations (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(255) NOT NULL,
    aggregation_type VARCHAR(50) NOT NULL, -- 'hourly', 'daily', 'weekly', 'monthly'
    value DECIMAL(15,6) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_api_metrics_timestamp ON api_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_metrics_service_name ON api_metrics(service_name);
CREATE INDEX IF NOT EXISTS idx_api_metrics_endpoint ON api_metrics(endpoint);
CREATE INDEX IF NOT EXISTS idx_api_metrics_status_code ON api_metrics(status_code);
CREATE INDEX IF NOT EXISTS idx_api_metrics_timestamp_service ON api_metrics(timestamp, service_name);
CREATE INDEX IF NOT EXISTS idx_custom_metrics_metric_name ON custom_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_custom_metrics_timestamp ON custom_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_custom_metrics_user_id ON custom_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_custom_metrics_tenant_id ON custom_metrics(tenant_id);
CREATE INDEX IF NOT EXISTS idx_custom_metrics_metric_timestamp ON custom_metrics(metric_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_metric_aggregations_metric_name ON metric_aggregations(metric_name);
CREATE INDEX IF NOT EXISTS idx_metric_aggregations_aggregation_type ON metric_aggregations(aggregation_type);
CREATE INDEX IF NOT EXISTS idx_metric_aggregations_start_time ON metric_aggregations(start_time);
CREATE INDEX IF NOT EXISTS idx_metric_aggregations_metric_type_time ON metric_aggregations(metric_name, aggregation_type, start_time);

-- Create partitioning for api_metrics table (if supported)
-- This creates monthly partitions for better query performance
-- Note: This requires PostgreSQL 10+ and may need to be set up manually
-- CREATE TABLE api_metrics_y2024m01 PARTITION OF api_metrics
--     FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

-- Create a function to automatically create monthly partitions
CREATE OR REPLACE FUNCTION create_monthly_partition(table_name text, start_date date)
RETURNS void AS $$
DECLARE
    partition_name text;
    end_date date;
BEGIN
    partition_name := table_name || '_y' || to_char(start_date, 'YYYY') || 'm' || to_char(start_date, 'MM');
    end_date := start_date + interval '1 month';
    
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                   partition_name, table_name, start_date, end_date);
END;
$$ LANGUAGE plpgsql;

-- Create a function to clean up old metrics data
CREATE OR REPLACE FUNCTION cleanup_old_metrics(retention_days integer DEFAULT 90)
RETURNS void AS $$
BEGIN
    -- Delete old API metrics
    DELETE FROM api_metrics 
    WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    -- Delete old custom metrics
    DELETE FROM custom_metrics 
    WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    -- Delete old aggregations (keep longer)
    DELETE FROM metric_aggregations 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * (retention_days * 2);
END;
$$ LANGUAGE plpgsql;
