from infrastructure.databases.core.base_migration import BaseMigration


class FixTenantBillingRecordsSchema(BaseMigration):
    """Fix tenant_billing_records table to match model: rename tenant_uuid to tenant_id, rename amount to cost, rename status to billing_status, add missing columns."""

    def up(self, adapter):
        """Run the migration."""
        # Step 1: Rename tenant_uuid to tenant_id if it exists
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'tenant_uuid'
                ) THEN
                    ALTER TABLE tenant_billing_records
                    RENAME COLUMN tenant_uuid TO tenant_id;
                END IF;
            END $$;
            """
        )
        
        # Step 2: Rename amount to cost if it exists
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'amount'
                ) THEN
                    ALTER TABLE tenant_billing_records
                    RENAME COLUMN amount TO cost;
                END IF;
            END $$;
            """
        )
        
        # Step 3: Change cost type to NUMERIC(20, 10) if needed
        # Only do this if cost column exists (either renamed from amount or already exists)
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'cost'
                ) THEN
                    ALTER TABLE tenant_billing_records
                    ALTER COLUMN cost TYPE NUMERIC(20, 10);
                END IF;
            END $$;
            """
        )
        
        # Step 4: Rename status to billing_status if it exists
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'status'
                ) THEN
                    ALTER TABLE tenant_billing_records
                    RENAME COLUMN status TO billing_status;
                END IF;
            END $$;
            """
        )
        
        # Step 5: Add billing_customer_id if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE tenant_billing_records
            ADD COLUMN IF NOT EXISTS billing_customer_id VARCHAR(255) NULL;
            """
        )
        
        # Step 6: Add suspension_reason if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE tenant_billing_records
            ADD COLUMN IF NOT EXISTS suspension_reason VARCHAR(512) NULL;
            """
        )
        
        # Step 7: Add suspended_until if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE tenant_billing_records
            ADD COLUMN IF NOT EXISTS suspended_until TIMESTAMP NULL;
            """
        )
        
        # Step 8: Remove unused columns (if they exist)
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'currency'
                ) THEN
                    ALTER TABLE tenant_billing_records DROP COLUMN currency;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'billing_period'
                ) THEN
                    ALTER TABLE tenant_billing_records DROP COLUMN billing_period;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'invoice_url'
                ) THEN
                    ALTER TABLE tenant_billing_records DROP COLUMN invoice_url;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'paid_at'
                ) THEN
                    ALTER TABLE tenant_billing_records DROP COLUMN paid_at;
                END IF;
            END $$;
            """
        )
        
        print("    ✓ Fixed tenant_billing_records schema")

    def down(self, adapter):
        """Rollback the migration."""
        # Note: This is a destructive migration, rollback is complex
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'tenant_id'
                ) THEN
                    ALTER TABLE tenant_billing_records
                    RENAME COLUMN tenant_id TO tenant_uuid;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'cost'
                ) THEN
                    ALTER TABLE tenant_billing_records
                    RENAME COLUMN cost TO amount;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_billing_records' 
                    AND column_name = 'billing_status'
                ) THEN
                    ALTER TABLE tenant_billing_records
                    RENAME COLUMN billing_status TO status;
                END IF;
            END $$;
            """
        )
        print("    ✓ Rolled back tenant_billing_records schema changes")
