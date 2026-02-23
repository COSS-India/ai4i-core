from infrastructure.databases.core.base_migration import BaseMigration


class FixUserBillingRecordsSchema(BaseMigration):
    """Fix user_billing_records table to match model: rename tenant_user_uuid to user_id, add missing columns, remove unused columns."""

    def up(self, adapter):
        """Run the migration."""
        # Step 1: Rename tenant_user_uuid to user_id if it exists
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'tenant_user_uuid'
                ) THEN
                    ALTER TABLE user_billing_records
                    RENAME COLUMN tenant_user_uuid TO user_id;
                END IF;
            END $$;
            """
        )
        
        # Step 2: Change user_id type to UUID if needed (should already be UUID)
        adapter.execute(
            """
            ALTER TABLE user_billing_records
            ALTER COLUMN user_id TYPE UUID USING user_id::uuid;
            """
        )
        
        # Step 3: Add tenant_id column if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE user_billing_records
            ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(255);
            """
        )
        
        # Step 4: Add foreign key for tenant_id if it doesn't exist
        adapter.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.table_constraints 
                    WHERE table_name = 'user_billing_records' 
                    AND constraint_name LIKE '%tenant_id%'
                ) THEN
                    ALTER TABLE user_billing_records
                    ADD CONSTRAINT fk_user_billing_records_tenant_id 
                    FOREIGN KEY (tenant_id) 
                    REFERENCES tenants(tenant_id) 
                    ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )
        
        # Step 5: Add service_name column if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE user_billing_records
            ADD COLUMN IF NOT EXISTS service_name VARCHAR(50);
            """
        )
        
        # Step 6: Add service_id column if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE user_billing_records
            ADD COLUMN IF NOT EXISTS service_id BIGINT;
            """
        )
        
        # Step 7: Add foreign key for service_id if it doesn't exist
        adapter.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.table_constraints 
                    WHERE table_name = 'user_billing_records' 
                    AND constraint_name LIKE '%service_id%'
                ) THEN
                    ALTER TABLE user_billing_records
                    ADD CONSTRAINT fk_user_billing_records_service_id 
                    FOREIGN KEY (service_id) 
                    REFERENCES service_config(id) 
                    ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )
        
        # Step 8: Rename amount to cost if it exists
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'amount'
                ) THEN
                    ALTER TABLE user_billing_records
                    RENAME COLUMN amount TO cost;
                END IF;
            END $$;
            """
        )
        
        # Step 9: Change cost type to NUMERIC(20, 10) if needed
        adapter.execute(
            """
            ALTER TABLE user_billing_records
            ALTER COLUMN cost TYPE NUMERIC(20, 10);
            """
        )
        
        # Step 10: Change billing_period from VARCHAR to DATE if needed
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'billing_period'
                    AND data_type = 'character varying'
                ) THEN
                    -- Try to convert VARCHAR to DATE (format: YYYY-MM)
                    ALTER TABLE user_billing_records
                    ALTER COLUMN billing_period TYPE DATE 
                    USING TO_DATE(billing_period || '-01', 'YYYY-MM-DD');
                END IF;
            END $$;
            """
        )
        
        # Step 11: Remove unused columns (if they exist)
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'currency'
                ) THEN
                    ALTER TABLE user_billing_records DROP COLUMN currency;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'invoice_url'
                ) THEN
                    ALTER TABLE user_billing_records DROP COLUMN invoice_url;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'paid_at'
                ) THEN
                    ALTER TABLE user_billing_records DROP COLUMN paid_at;
                END IF;
            END $$;
            """
        )
        
        # Step 12: Populate data for new columns before setting NOT NULL
        # Populate tenant_id from tenant_users if possible
        adapter.execute(
            """
            DO $$
            BEGIN
                -- Try to populate tenant_id from tenant_users relationship
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'user_id'
                ) AND EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_users' 
                    AND column_name = 'tenant_id'
                ) THEN
                    UPDATE user_billing_records ubr
                    SET tenant_id = tu.tenant_id
                    FROM tenant_users tu
                    WHERE ubr.user_id = tu.id
                    AND ubr.tenant_id IS NULL;
                END IF;
            END $$;
            """
        )
        
        # Step 13: Set NOT NULL constraints for required columns (only if no NULLs exist)
        adapter.execute(
            """
            DO $$
            BEGIN
                -- Only set NOT NULL if all rows have values
                IF NOT EXISTS (SELECT 1 FROM user_billing_records WHERE tenant_id IS NULL) THEN
                    ALTER TABLE user_billing_records ALTER COLUMN tenant_id SET NOT NULL;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM user_billing_records WHERE service_name IS NULL) THEN
                    ALTER TABLE user_billing_records ALTER COLUMN service_name SET NOT NULL;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM user_billing_records WHERE service_id IS NULL) THEN
                    ALTER TABLE user_billing_records ALTER COLUMN service_id SET NOT NULL;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM user_billing_records WHERE cost IS NULL) THEN
                    ALTER TABLE user_billing_records ALTER COLUMN cost SET NOT NULL;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM user_billing_records WHERE billing_period IS NULL) THEN
                    ALTER TABLE user_billing_records ALTER COLUMN billing_period SET NOT NULL;
                END IF;
            END $$;
            """
        )
        
        print("    ✓ Fixed user_billing_records schema")
        print("    ⚠ Note: If tenant_id, service_name, or service_id columns have NULL values, NOT NULL constraints were not applied. Please populate data and run migration again.")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'user_id'
                ) THEN
                    ALTER TABLE user_billing_records
                    RENAME COLUMN user_id TO tenant_user_uuid;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_billing_records' 
                    AND column_name = 'cost'
                ) THEN
                    ALTER TABLE user_billing_records
                    RENAME COLUMN cost TO amount;
                END IF;
            END $$;
            """
        )
        print("    ✓ Rolled back user_billing_records schema changes")
