-- =============================================================================
-- Init Alerting DB - Dynamic Alert Configuration Schema
-- =============================================================================
-- This script creates alerting_db (if missing) and all tables, indexes,
-- triggers, and audit logic for dynamic alert management (API-driven config).
--
-- Usage:
--   psql -h <host> -U <user> -d postgres -f init_alerting_db.sql
-- Or if alerting_db already exists and you only want schema inside it:
--   psql -h <host> -U <user> -d alerting_db -f init_alerting_db_schema_only.sql
--   (use the section below "Connect to alerting_db" only)
-- =============================================================================

-- Allow execution to continue if database already exists
\set ON_ERROR_STOP off
\c postgres;
CREATE DATABASE alerting_db;
\set ON_ERROR_STOP on

-- Connect to alerting_db to create the schema
\c alerting_db;

-- =============================================================================
-- Tables
-- =============================================================================

-- Alert Definitions Table
-- Stores complete PromQL expressions per organization with all metadata
CREATE TABLE IF NOT EXISTS alert_definitions (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    promql_expr TEXT NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT 'application',
    sub_category VARCHAR(100),
    signal VARCHAR(100),
    signal_metric VARCHAR(100),
    condition_operator VARCHAR(10),
    severity VARCHAR(20) NOT NULL,
    urgency VARCHAR(20) DEFAULT 'medium',
    alert_type VARCHAR(50),
    scope VARCHAR(50),
    service TEXT[],
    evaluation_interval VARCHAR(20) DEFAULT '30s',
    for_duration VARCHAR(20) DEFAULT '5m',
    threshold_value DOUBLE PRECISION,
    threshold_unit VARCHAR(50),
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    CONSTRAINT unique_organization_alert_name UNIQUE (organization, name)
);

-- Annotations for alert definitions (summary, description, impact, action)
CREATE TABLE IF NOT EXISTS alert_annotations (
    id SERIAL PRIMARY KEY,
    alert_definition_id INTEGER NOT NULL REFERENCES alert_definitions(id) ON DELETE CASCADE,
    annotation_key VARCHAR(50) NOT NULL,
    annotation_value TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_alert_annotation_key UNIQUE (alert_definition_id, annotation_key)
);

-- Notification Receivers Table
CREATE TABLE IF NOT EXISTS notification_receivers (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL,
    receiver_name VARCHAR(255) NOT NULL,
    rule_name VARCHAR(255),
    email_to TEXT[] NOT NULL DEFAULT '{}',
    rbac_role VARCHAR(50),
    alert_names TEXT[],
    tenant VARCHAR(255),
    email_subject_template TEXT,
    email_body_template TEXT,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    CONSTRAINT unique_organization_receiver_name UNIQUE (organization, receiver_name)
);

-- Routing Rules Table
CREATE TABLE IF NOT EXISTS routing_rules (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100) NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    receiver_id INTEGER NOT NULL REFERENCES notification_receivers(id) ON DELETE CASCADE,
    match_severity VARCHAR(20),
    match_category VARCHAR(50),
    match_alert_type VARCHAR(50),
    match_alert_names TEXT[],
    match_tenant_id VARCHAR(255),
    group_by TEXT[],
    group_wait VARCHAR(20) DEFAULT '10s',
    group_interval VARCHAR(20) DEFAULT '10s',
    repeat_interval VARCHAR(20) DEFAULT '12h',
    continue_routing BOOLEAN DEFAULT false,
    priority INTEGER DEFAULT 100,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    CONSTRAINT unique_organization_rule_name UNIQUE (organization, rule_name)
);

-- Alert History Table
-- Read-only audit log of triggered alerts, populated from Alertmanager webhooks
CREATE TABLE IF NOT EXISTS alert_history (
    id BIGSERIAL PRIMARY KEY,
    alert_name VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    triggered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'firing',
    receiver VARCHAR(255) NOT NULL,
    notified_display VARCHAR(500),
    tenant VARCHAR(255),
    organization VARCHAR(255),
    labels JSONB,
    annotations JSONB,
    fingerprint VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Audit Log Table
CREATE TABLE IF NOT EXISTS alert_config_audit_log (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(100),
    table_name VARCHAR(50) NOT NULL,
    record_id INTEGER NOT NULL,
    operation VARCHAR(20) NOT NULL,
    changed_by VARCHAR(100) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    before_values JSONB,
    after_values JSONB,
    change_description TEXT
);

-- =============================================================================
-- Indexes
-- =============================================================================

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

CREATE INDEX IF NOT EXISTS idx_alert_history_triggered_at ON alert_history(triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_history_category ON alert_history(category);
CREATE INDEX IF NOT EXISTS idx_alert_history_severity ON alert_history(severity);
CREATE INDEX IF NOT EXISTS idx_alert_history_alert_name ON alert_history(alert_name);
CREATE INDEX IF NOT EXISTS idx_alert_history_tenant ON alert_history(tenant);

CREATE INDEX IF NOT EXISTS idx_audit_log_organization ON alert_config_audit_log(organization);
CREATE INDEX IF NOT EXISTS idx_audit_log_table_record ON alert_config_audit_log(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON alert_config_audit_log(changed_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_by ON alert_config_audit_log(changed_by);

-- =============================================================================
-- Trigger: updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_alert_config_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_alert_definitions_updated_at ON alert_definitions;
CREATE TRIGGER update_alert_definitions_updated_at
    BEFORE UPDATE ON alert_definitions
    FOR EACH ROW EXECUTE PROCEDURE update_alert_config_updated_at();

DROP TRIGGER IF EXISTS update_alert_annotations_updated_at ON alert_annotations;
CREATE TRIGGER update_alert_annotations_updated_at
    BEFORE UPDATE ON alert_annotations
    FOR EACH ROW EXECUTE PROCEDURE update_alert_config_updated_at();

DROP TRIGGER IF EXISTS update_notification_receivers_updated_at ON notification_receivers;
CREATE TRIGGER update_notification_receivers_updated_at
    BEFORE UPDATE ON notification_receivers
    FOR EACH ROW EXECUTE PROCEDURE update_alert_config_updated_at();

DROP TRIGGER IF EXISTS update_routing_rules_updated_at ON routing_rules;
CREATE TRIGGER update_routing_rules_updated_at
    BEFORE UPDATE ON routing_rules
    FOR EACH ROW EXECUTE PROCEDURE update_alert_config_updated_at();

-- =============================================================================
-- Trigger: Audit log
-- =============================================================================

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

DROP TRIGGER IF EXISTS audit_alert_definitions_changes ON alert_definitions;
CREATE TRIGGER audit_alert_definitions_changes
    AFTER INSERT OR UPDATE OR DELETE ON alert_definitions
    FOR EACH ROW EXECUTE PROCEDURE log_alert_config_changes();

DROP TRIGGER IF EXISTS audit_notification_receivers_changes ON notification_receivers;
CREATE TRIGGER audit_notification_receivers_changes
    AFTER INSERT OR UPDATE OR DELETE ON notification_receivers
    FOR EACH ROW EXECUTE PROCEDURE log_alert_config_changes();

DROP TRIGGER IF EXISTS audit_routing_rules_changes ON routing_rules;
CREATE TRIGGER audit_routing_rules_changes
    AFTER INSERT OR UPDATE OR DELETE ON routing_rules
    FOR EACH ROW EXECUTE PROCEDURE log_alert_config_changes();

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE alert_definitions IS 'Stores organization-specific alert definitions with complete PromQL expressions';
COMMENT ON COLUMN alert_definitions.service IS 'Optional list of service names (e.g. asr-service, nmt-service); when set, PromQL includes service label matcher';
COMMENT ON COLUMN alert_definitions.threshold_value IS 'Numeric threshold for threshold-based PromQL generation';
COMMENT ON COLUMN alert_definitions.threshold_unit IS 'Unit for threshold (e.g. ms, %, count)';
COMMENT ON TABLE alert_annotations IS 'Stores annotations (summary, description, impact, action) for alert definitions';
COMMENT ON TABLE notification_receivers IS 'Stores notification channel configurations (email, RBAC role) per organization; optional alert_names and tenant for scoped routing';
COMMENT ON TABLE routing_rules IS 'Defines routing rules that match alerts to receivers based on severity/category/alert_names/tenant_id';
COMMENT ON TABLE alert_config_audit_log IS 'Audit trail of all changes to alert configurations for compliance';
COMMENT ON TABLE alert_history IS 'Read-only audit log of triggered alerts populated from Alertmanager webhooks';
