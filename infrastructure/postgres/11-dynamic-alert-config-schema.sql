-- Dynamic Alert Configuration Schema
-- This schema enables customer-specific alert configuration via API instead of manual YAML editing
-- Connect to alerting_db and create tables for dynamic alert management

-- Allow execution to continue even if database already exists
\set ON_ERROR_STOP off

-- Create alerting_db if it doesn't exist
-- Note: Must be connected to a template database (e.g., postgres) to create a new database
\c postgres;
CREATE DATABASE alerting_db;
\set ON_ERROR_STOP on

-- Now connect to alerting_db to create the schema
\c alerting_db;

-- Alert Definitions Table
-- Stores complete PromQL expressions per customer with all metadata
CREATE TABLE IF NOT EXISTS alert_definitions (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL, -- Organization identifier (e.g., 'irctc', 'kisanmitra')
    name VARCHAR(255) NOT NULL, -- Alert name (e.g., 'HighLatency')
    description TEXT,
    promql_expr TEXT NOT NULL, -- Complete PromQL expression with organization filter and threshold embedded
    category VARCHAR(50) NOT NULL DEFAULT 'application', -- 'application' or 'infrastructure'
    severity VARCHAR(20) NOT NULL, -- 'critical', 'warning', 'info'
    urgency VARCHAR(20) DEFAULT 'medium', -- 'high', 'medium', 'low'
    alert_type VARCHAR(50), -- 'latency', 'error_rate', 'cpu', etc.
    scope VARCHAR(50), -- 'all_services', 'per_service', 'per_endpoint', 'cluster', etc.
    evaluation_interval VARCHAR(20) DEFAULT '30s', -- Prometheus evaluation interval
    for_duration VARCHAR(20) DEFAULT '5m', -- Duration before alert fires
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    -- Ensure unique alert name per organization
    CONSTRAINT unique_organization_alert_name UNIQUE (organization, name)
);

-- Annotations for alert definitions (summary, description, impact, action)
CREATE TABLE IF NOT EXISTS alert_annotations (
    id SERIAL PRIMARY KEY,
    alert_definition_id INTEGER NOT NULL REFERENCES alert_definitions(id) ON DELETE CASCADE,
    annotation_key VARCHAR(50) NOT NULL, -- 'summary', 'description', 'impact', 'action'
    annotation_value TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_alert_annotation_key UNIQUE (alert_definition_id, annotation_key)
);

-- Notification Receivers Table
-- Stores email configurations per customer
CREATE TABLE IF NOT EXISTS notification_receivers (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL,
    receiver_name VARCHAR(255) NOT NULL, -- Unique receiver name per customer
    -- Email configuration
    email_to TEXT[] NOT NULL, -- Array of email addresses (required)
    rbac_role VARCHAR(50), -- RBAC role name (ADMIN, MODERATOR, USER, GUEST) - if set, email_to will be resolved from users with this role
    email_subject_template TEXT, -- Custom subject template
    email_body_template TEXT, -- Custom HTML body template
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    -- Ensure unique receiver name per organization
    CONSTRAINT unique_organization_receiver_name UNIQUE (organization, receiver_name)
);

-- Routing Rules Table
-- Defines which alerts go to which receivers based on severity/category
CREATE TABLE IF NOT EXISTS routing_rules (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    receiver_id INTEGER NOT NULL REFERENCES notification_receivers(id) ON DELETE CASCADE,
    -- Match conditions (all must match for rule to apply)
    match_severity VARCHAR(20), -- 'critical', 'warning', 'info', or NULL (matches all)
    match_category VARCHAR(50), -- 'application', 'infrastructure', or NULL (matches all)
    match_alert_type VARCHAR(50), -- Specific alert type or NULL (matches all)
    -- Routing behavior
    group_by TEXT[], -- Array of label names to group by (e.g., ['alertname', 'category', 'severity'])
    group_wait VARCHAR(20) DEFAULT '10s',
    group_interval VARCHAR(20) DEFAULT '10s',
    repeat_interval VARCHAR(20) DEFAULT '12h',
    continue_routing BOOLEAN DEFAULT false, -- If true, continue to next matching rule
    priority INTEGER DEFAULT 100, -- Lower number = higher priority (evaluated first)
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    -- Ensure unique rule name per organization
    CONSTRAINT unique_organization_rule_name UNIQUE (organization, rule_name)
);

-- Audit Log Table
-- Records all changes to alert configurations for compliance and troubleshooting
CREATE TABLE IF NOT EXISTS alert_config_audit_log (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100),
    table_name VARCHAR(50) NOT NULL, -- 'alert_definitions', 'notification_receivers', 'routing_rules'
    record_id INTEGER NOT NULL,
    operation VARCHAR(20) NOT NULL, -- 'CREATE', 'UPDATE', 'DELETE'
    changed_by VARCHAR(100) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Store before/after values as JSON for detailed audit trail
    before_values JSONB,
    after_values JSONB,
    change_description TEXT
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_alert_definitions_organization ON alert_definitions(organization);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_enabled ON alert_definitions(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_category ON alert_definitions(category);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_severity ON alert_definitions(severity);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_organization_enabled ON alert_definitions(organization, enabled);

CREATE INDEX IF NOT EXISTS idx_alert_annotations_alert_def_id ON alert_annotations(alert_definition_id);

CREATE INDEX IF NOT EXISTS idx_notification_receivers_organization ON notification_receivers(organization);
CREATE INDEX IF NOT EXISTS idx_notification_receivers_enabled ON notification_receivers(enabled);

CREATE INDEX IF NOT EXISTS idx_routing_rules_organization ON routing_rules(organization);
CREATE INDEX IF NOT EXISTS idx_routing_rules_receiver_id ON routing_rules(receiver_id);
CREATE INDEX IF NOT EXISTS idx_routing_rules_enabled ON routing_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_routing_rules_priority ON routing_rules(priority);
CREATE INDEX IF NOT EXISTS idx_routing_rules_match_severity ON routing_rules(match_severity);
CREATE INDEX IF NOT EXISTS idx_routing_rules_match_category ON routing_rules(match_category);

CREATE INDEX IF NOT EXISTS idx_audit_log_organization ON alert_config_audit_log(organization);
CREATE INDEX IF NOT EXISTS idx_audit_log_table_record ON alert_config_audit_log(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON alert_config_audit_log(changed_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_by ON alert_config_audit_log(changed_by);

-- Create trigger function for updated_at
CREATE OR REPLACE FUNCTION update_alert_config_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at columns
CREATE TRIGGER update_alert_definitions_updated_at 
    BEFORE UPDATE ON alert_definitions
    FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();

CREATE TRIGGER update_alert_annotations_updated_at 
    BEFORE UPDATE ON alert_annotations
    FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();

CREATE TRIGGER update_notification_receivers_updated_at 
    BEFORE UPDATE ON notification_receivers
    FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();

CREATE TRIGGER update_routing_rules_updated_at 
    BEFORE UPDATE ON routing_rules
    FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();

-- Create audit log trigger function
CREATE OR REPLACE FUNCTION log_alert_config_changes()
RETURNS TRIGGER AS $$
DECLARE
    v_organization VARCHAR(100);
    v_table_name VARCHAR(50);
    v_record_id INTEGER;
    v_operation VARCHAR(20);
    v_changed_by VARCHAR(100);
    v_before_values JSONB;
    v_after_values JSONB;
BEGIN
    -- Determine table name and organization based on which table triggered
    IF TG_TABLE_NAME = 'alert_definitions' THEN
        v_table_name := 'alert_definitions';
        v_record_id := COALESCE(NEW.id, OLD.id);
        v_organization := COALESCE(NEW.organization, OLD.organization);
        v_changed_by := COALESCE(NEW.updated_by, NEW.created_by, OLD.updated_by, OLD.created_by, 'system');
        
        IF TG_OP = 'INSERT' THEN
            v_operation := 'CREATE';
            v_after_values := to_jsonb(NEW);
            v_before_values := NULL;
        ELSIF TG_OP = 'UPDATE' THEN
            v_operation := 'UPDATE';
            v_before_values := to_jsonb(OLD);
            v_after_values := to_jsonb(NEW);
        ELSIF TG_OP = 'DELETE' THEN
            v_operation := 'DELETE';
            v_before_values := to_jsonb(OLD);
            v_after_values := NULL;
        END IF;
        
    ELSIF TG_TABLE_NAME = 'notification_receivers' THEN
        v_table_name := 'notification_receivers';
        v_record_id := COALESCE(NEW.id, OLD.id);
        v_organization := COALESCE(NEW.organization, OLD.organization);
        -- notification_receivers doesn't have updated_by column, only created_by
        v_changed_by := COALESCE(NEW.created_by, OLD.created_by, 'system');
        
        IF TG_OP = 'INSERT' THEN
            v_operation := 'CREATE';
            v_after_values := to_jsonb(NEW);
            v_before_values := NULL;
        ELSIF TG_OP = 'UPDATE' THEN
            v_operation := 'UPDATE';
            v_before_values := to_jsonb(OLD);
            v_after_values := to_jsonb(NEW);
        ELSIF TG_OP = 'DELETE' THEN
            v_operation := 'DELETE';
            v_before_values := to_jsonb(OLD);
            v_after_values := NULL;
        END IF;
        
    ELSIF TG_TABLE_NAME = 'routing_rules' THEN
        v_table_name := 'routing_rules';
        v_record_id := COALESCE(NEW.id, OLD.id);
        v_organization := COALESCE(NEW.organization, OLD.organization);
        -- routing_rules doesn't have updated_by column, only created_by
        v_changed_by := COALESCE(NEW.created_by, OLD.created_by, 'system');
        
        IF TG_OP = 'INSERT' THEN
            v_operation := 'CREATE';
            v_after_values := to_jsonb(NEW);
            v_before_values := NULL;
        ELSIF TG_OP = 'UPDATE' THEN
            v_operation := 'UPDATE';
            v_before_values := to_jsonb(OLD);
            v_after_values := to_jsonb(NEW);
        ELSIF TG_OP = 'DELETE' THEN
            v_operation := 'DELETE';
            v_before_values := to_jsonb(OLD);
            v_after_values := NULL;
        END IF;
    END IF;
    
    -- Insert audit log entry
    INSERT INTO alert_config_audit_log (
        organization,
        table_name,
        record_id,
        operation,
        changed_by,
        before_values,
        after_values
    ) VALUES (
        v_organization,
        v_table_name,
        v_record_id,
        v_operation,
        v_changed_by,
        v_before_values,
        v_after_values
    );
    
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create audit triggers
CREATE TRIGGER audit_alert_definitions_changes
    AFTER INSERT OR UPDATE OR DELETE ON alert_definitions
    FOR EACH ROW EXECUTE FUNCTION log_alert_config_changes();

CREATE TRIGGER audit_notification_receivers_changes
    AFTER INSERT OR UPDATE OR DELETE ON notification_receivers
    FOR EACH ROW EXECUTE FUNCTION log_alert_config_changes();

CREATE TRIGGER audit_routing_rules_changes
    AFTER INSERT OR UPDATE OR DELETE ON routing_rules
    FOR EACH ROW EXECUTE FUNCTION log_alert_config_changes();

-- Add comments for documentation
COMMENT ON TABLE alert_definitions IS 'Stores organization-specific alert definitions with complete PromQL expressions';
COMMENT ON TABLE alert_annotations IS 'Stores annotations (summary, description, impact, action) for alert definitions';
COMMENT ON TABLE notification_receivers IS 'Stores notification channel configurations (email) per organization';
COMMENT ON TABLE routing_rules IS 'Defines routing rules that match alerts to receivers based on severity/category';
COMMENT ON TABLE alert_config_audit_log IS 'Audit trail of all changes to alert configurations for compliance';

