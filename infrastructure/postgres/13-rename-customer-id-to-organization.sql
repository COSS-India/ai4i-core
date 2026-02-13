-- Migration script to rename customer_id to organization
-- Run this script on existing databases to migrate from customer_id to organization
-- Usage: docker exec -i ai4v-postgres psql -U dhruva_user -d alerting_db < infrastructure/postgres/13-rename-customer-id-to-organization.sql

\c alerting_db;

-- Rename columns in all tables (only if they exist)
DO $$
BEGIN
    -- Check and rename alert_definitions.customer_id
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'alert_definitions' AND column_name = 'customer_id') THEN
        ALTER TABLE alert_definitions RENAME COLUMN customer_id TO organization;
        RAISE NOTICE 'Renamed alert_definitions.customer_id to organization';
    END IF;
    
    -- Check and rename notification_receivers.customer_id
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'notification_receivers' AND column_name = 'customer_id') THEN
        ALTER TABLE notification_receivers RENAME COLUMN customer_id TO organization;
        RAISE NOTICE 'Renamed notification_receivers.customer_id to organization';
    END IF;
    
    -- Check and rename routing_rules.customer_id
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'routing_rules' AND column_name = 'customer_id') THEN
        ALTER TABLE routing_rules RENAME COLUMN customer_id TO organization;
        RAISE NOTICE 'Renamed routing_rules.customer_id to organization';
    END IF;
    
    -- Check and rename alert_config_audit_log.customer_id
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'alert_config_audit_log' AND column_name = 'customer_id') THEN
        ALTER TABLE alert_config_audit_log RENAME COLUMN customer_id TO organization;
        RAISE NOTICE 'Renamed alert_config_audit_log.customer_id to organization';
    END IF;
END $$;

-- Rename constraints (only if they exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name = 'unique_customer_alert_name' AND table_name = 'alert_definitions') THEN
        ALTER TABLE alert_definitions RENAME CONSTRAINT unique_customer_alert_name TO unique_organization_alert_name;
        RAISE NOTICE 'Renamed constraint unique_customer_alert_name to unique_organization_alert_name';
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name = 'unique_customer_receiver_name' AND table_name = 'notification_receivers') THEN
        ALTER TABLE notification_receivers RENAME CONSTRAINT unique_customer_receiver_name TO unique_organization_receiver_name;
        RAISE NOTICE 'Renamed constraint unique_customer_receiver_name to unique_organization_receiver_name';
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name = 'unique_customer_rule_name' AND table_name = 'routing_rules') THEN
        ALTER TABLE routing_rules RENAME CONSTRAINT unique_customer_rule_name TO unique_organization_rule_name;
        RAISE NOTICE 'Renamed constraint unique_customer_rule_name to unique_organization_rule_name';
    END IF;
END $$;

-- Drop old indexes
DROP INDEX IF EXISTS idx_alert_definitions_customer_id;
DROP INDEX IF EXISTS idx_alert_definitions_customer_enabled;
DROP INDEX IF EXISTS idx_notification_receivers_customer_id;
DROP INDEX IF EXISTS idx_routing_rules_customer_id;
DROP INDEX IF EXISTS idx_audit_log_customer_id;

-- Create new indexes with organization name
CREATE INDEX IF NOT EXISTS idx_alert_definitions_organization ON alert_definitions(organization);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_organization_enabled ON alert_definitions(organization, enabled);
CREATE INDEX IF NOT EXISTS idx_notification_receivers_organization ON notification_receivers(organization);
CREATE INDEX IF NOT EXISTS idx_routing_rules_organization ON routing_rules(organization);
CREATE INDEX IF NOT EXISTS idx_audit_log_organization ON alert_config_audit_log(organization);

-- Update the audit trigger function to use organization instead of customer_id
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

-- Verify migration
SELECT 'Migration completed. Verifying...' AS status;
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name IN ('alert_definitions', 'notification_receivers', 'routing_rules', 'alert_config_audit_log')
  AND column_name IN ('customer_id', 'organization')
ORDER BY table_name, column_name;
