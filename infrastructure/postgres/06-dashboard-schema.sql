-- Dashboard Service Database Schema
-- Connect to dashboard_db and create tables for dashboard management

\c dashboard_db;

-- Dashboards table
CREATE TABLE IF NOT EXISTS dashboards (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    layout JSONB NOT NULL, -- Dashboard layout configuration
    is_public BOOLEAN DEFAULT false,
    owner_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Dashboard widgets table
CREATE TABLE IF NOT EXISTS dashboard_widgets (
    id SERIAL PRIMARY KEY,
    dashboard_id INTEGER REFERENCES dashboards(id) ON DELETE CASCADE,
    widget_type VARCHAR(100) NOT NULL, -- 'chart', 'metric', 'table', 'gauge', 'map'
    configuration JSONB NOT NULL, -- Widget configuration and settings
    position JSONB NOT NULL, -- Position and size information
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Saved queries table
CREATE TABLE IF NOT EXISTS saved_queries (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    query TEXT NOT NULL,
    parameters JSONB, -- Query parameters and filters
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Reports table
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    schedule VARCHAR(100), -- Cron expression for scheduled reports
    recipients TEXT[], -- Array of email addresses
    format VARCHAR(20) DEFAULT 'pdf', -- 'pdf', 'excel', 'csv'
    query_id INTEGER REFERENCES saved_queries(id) ON DELETE SET NULL,
    last_generated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- User preferences table
CREATE TABLE IF NOT EXISTS user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    preferences JSONB NOT NULL, -- User-specific dashboard preferences
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_dashboards_owner_id ON dashboards(owner_id);
CREATE INDEX IF NOT EXISTS idx_dashboards_is_public ON dashboards(is_public);
CREATE INDEX IF NOT EXISTS idx_dashboards_created_at ON dashboards(created_at);
CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_dashboard_id ON dashboard_widgets(dashboard_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_widget_type ON dashboard_widgets(widget_type);
CREATE INDEX IF NOT EXISTS idx_saved_queries_created_by ON saved_queries(created_by);
CREATE INDEX IF NOT EXISTS idx_saved_queries_created_at ON saved_queries(created_at);
CREATE INDEX IF NOT EXISTS idx_reports_query_id ON reports(query_id);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at);
CREATE INDEX IF NOT EXISTS idx_reports_last_generated ON reports(last_generated_at);
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns
CREATE TRIGGER update_dashboards_updated_at BEFORE UPDATE ON dashboards
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_dashboard_widgets_updated_at BEFORE UPDATE ON dashboard_widgets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_saved_queries_updated_at BEFORE UPDATE ON saved_queries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_reports_updated_at BEFORE UPDATE ON reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_preferences_updated_at BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create a function to get dashboard with widgets
CREATE OR REPLACE FUNCTION get_dashboard_with_widgets(dashboard_id integer)
RETURNS TABLE (
    dashboard_id integer,
    dashboard_name varchar(255),
    dashboard_description text,
    dashboard_layout jsonb,
    is_public boolean,
    owner_id integer,
    widget_id integer,
    widget_type varchar(100),
    widget_configuration jsonb,
    widget_position jsonb
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        d.id as dashboard_id,
        d.name as dashboard_name,
        d.description as dashboard_description,
        d.layout as dashboard_layout,
        d.is_public,
        d.owner_id,
        w.id as widget_id,
        w.widget_type,
        w.configuration as widget_configuration,
        w.position as widget_position
    FROM dashboards d
    LEFT JOIN dashboard_widgets w ON d.id = w.dashboard_id
    WHERE d.id = dashboard_id
    ORDER BY w.id;
END;
$$ LANGUAGE plpgsql;

-- Create a function to clean up old dashboard data
CREATE OR REPLACE FUNCTION cleanup_old_dashboard_data(retention_days integer DEFAULT 365)
RETURNS void AS $$
BEGIN
    -- Delete old reports that haven't been generated recently
    DELETE FROM reports 
    WHERE last_generated_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days
    OR (last_generated_at IS NULL AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days);
    
    -- Delete old saved queries that are not referenced by reports
    DELETE FROM saved_queries 
    WHERE id NOT IN (SELECT DISTINCT query_id FROM reports WHERE query_id IS NOT NULL)
    AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
END;
$$ LANGUAGE plpgsql;
