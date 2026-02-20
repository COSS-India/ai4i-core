from infrastructure.databases.core.base_migration import BaseMigration

class CreateAlertAuditTriggers(BaseMigration):
    """Create audit triggers for dynamic alert configuration in alerting_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create updated_at trigger function for dynamic tables
        adapter.execute("""
            CREATE OR REPLACE FUNCTION update_alert_config_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created update_alert_config_updated_at function")

        # Create triggers for updated_at columns (idempotent: skip if already exist)
        for trigger_name, table_name in [
            ("update_alert_definitions_updated_at", "alert_definitions"),
            ("update_alert_annotations_updated_at", "alert_annotations"),
            ("update_notification_receivers_updated_at", "notification_receivers"),
            ("update_routing_rules_updated_at", "routing_rules"),
        ]:
            adapter.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = '{trigger_name}')
                    THEN
                        CREATE TRIGGER {trigger_name}
                            BEFORE UPDATE ON {table_name}
                            FOR EACH ROW EXECUTE FUNCTION update_alert_config_updated_at();
                    END IF;
                END $$;
            """)
        print("    ✓ Created updated_at triggers for dynamic alert config")

        # Create audit log trigger function (complex)
        adapter.execute("""
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
        """)
        print("    ✓ Created log_alert_config_changes function")

        # Create audit triggers (idempotent: skip if already exist)
        for trigger_name, table_name in [
            ("audit_alert_definitions_changes", "alert_definitions"),
            ("audit_notification_receivers_changes", "notification_receivers"),
            ("audit_routing_rules_changes", "routing_rules"),
        ]:
            adapter.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = '{trigger_name}')
                    THEN
                        CREATE TRIGGER {trigger_name}
                            AFTER INSERT OR UPDATE OR DELETE ON {table_name}
                            FOR EACH ROW EXECUTE FUNCTION log_alert_config_changes();
                    END IF;
                END $$;
            """)
        print("    ✓ Created audit triggers for alert configuration changes")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TRIGGER IF EXISTS audit_routing_rules_changes ON routing_rules;
            DROP TRIGGER IF EXISTS audit_notification_receivers_changes ON notification_receivers;
            DROP TRIGGER IF EXISTS audit_alert_definitions_changes ON alert_definitions;
            DROP FUNCTION IF EXISTS log_alert_config_changes CASCADE;
            DROP TRIGGER IF EXISTS update_routing_rules_updated_at ON routing_rules;
            DROP TRIGGER IF EXISTS update_notification_receivers_updated_at ON notification_receivers;
            DROP TRIGGER IF EXISTS update_alert_annotations_updated_at ON alert_annotations;
            DROP TRIGGER IF EXISTS update_alert_definitions_updated_at ON alert_definitions;
            DROP FUNCTION IF EXISTS update_alert_config_updated_at CASCADE;
        """)
        print("    ✓ Dropped alert audit triggers and functions")
