from infrastructure.databases.core.base_migration import BaseMigration


class FixAlertAuditTrigger(BaseMigration):
    """Fix audit trigger function to handle tables without updated_by column."""

    def up(self, adapter):
        """Run the migration."""
        adapter.execute("""
            -- Fix audit trigger function to handle tables without updated_by column
            -- This fixes the error: record "new" has no field "updated_by"
            -- for notification_receivers and routing_rules tables
            
            CREATE OR REPLACE FUNCTION log_alert_config_changes()
            RETURNS TRIGGER AS $$
            DECLARE
                v_customer_id VARCHAR(100);
                v_table_name VARCHAR(50);
                v_record_id INTEGER;
                v_operation VARCHAR(20);
                v_changed_by VARCHAR(100);
                v_before_values JSONB;
                v_after_values JSONB;
            BEGIN
                -- Determine table name and customer_id based on which table triggered
                IF TG_TABLE_NAME = 'alert_definitions' THEN
                    v_table_name := 'alert_definitions';
                    v_record_id := COALESCE(NEW.id, OLD.id);
                    v_customer_id := COALESCE(NEW.customer_id, OLD.customer_id);
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
                    v_customer_id := COALESCE(NEW.customer_id, OLD.customer_id);
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
                    v_customer_id := COALESCE(NEW.customer_id, OLD.customer_id);
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
                    table_name, record_id, operation, changed_by, customer_id,
                    before_values, after_values
                ) VALUES (
                    v_table_name, v_record_id, v_operation, v_changed_by, v_customer_id,
                    v_before_values, v_after_values
                );
                
                -- Return appropriate record
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                ELSE
                    RETURN NEW;
                END IF;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Fixed audit trigger function to handle tables without updated_by column")

    def down(self, adapter):
        """Rollback the migration."""
        # Rollback would restore the original buggy version, but that's not useful
        # Just keep the fixed version even on rollback
        print("    ✓ Keeping fixed audit trigger function (rollback not needed)")
