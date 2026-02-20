from infrastructure.databases.core.base_migration import BaseMigration


class FixTenantAuditLogsSchema(BaseMigration):
    """Fix tenant_audit_logs table to match model: rename tenant_uuid to tenant_id, add actor/details/updated_at, remove unused columns."""

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
                    WHERE table_name = 'tenant_audit_logs' 
                    AND column_name = 'tenant_uuid'
                ) THEN
                    ALTER TABLE tenant_audit_logs
                    RENAME COLUMN tenant_uuid TO tenant_id;
                END IF;
            END $$;
            """
        )
        
        # Step 2: Add actor column if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE tenant_audit_logs
            ADD COLUMN IF NOT EXISTS actor VARCHAR(50);
            """
        )
        
        # Step 3: Set default value for actor
        adapter.execute(
            """
            UPDATE tenant_audit_logs
            SET actor = 'system'
            WHERE actor IS NULL;
            """
        )
        
        # Step 4: Set actor to NOT NULL
        adapter.execute(
            """
            ALTER TABLE tenant_audit_logs
            ALTER COLUMN actor SET NOT NULL,
            ALTER COLUMN actor SET DEFAULT 'system';
            """
        )
        
        # Step 5: Add details column if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE tenant_audit_logs
            ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb;
            """
        )
        
        # Step 6: Add updated_at column if it doesn't exist
        adapter.execute(
            """
            ALTER TABLE tenant_audit_logs
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
            """
        )
        
        # Step 7: Remove unused columns (if they exist)
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_audit_logs' 
                    AND column_name = 'user_id'
                ) THEN
                    ALTER TABLE tenant_audit_logs DROP COLUMN user_id;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_audit_logs' 
                    AND column_name = 'resource_type'
                ) THEN
                    ALTER TABLE tenant_audit_logs DROP COLUMN resource_type;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_audit_logs' 
                    AND column_name = 'resource_id'
                ) THEN
                    ALTER TABLE tenant_audit_logs DROP COLUMN resource_id;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_audit_logs' 
                    AND column_name = 'changes'
                ) THEN
                    ALTER TABLE tenant_audit_logs DROP COLUMN changes;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_audit_logs' 
                    AND column_name = 'ip_address'
                ) THEN
                    ALTER TABLE tenant_audit_logs DROP COLUMN ip_address;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_audit_logs' 
                    AND column_name = 'user_agent'
                ) THEN
                    ALTER TABLE tenant_audit_logs DROP COLUMN user_agent;
                END IF;
            END $$;
            """
        )
        
        # Step 8: Update action column length to match model (VARCHAR(50))
        adapter.execute(
            """
            ALTER TABLE tenant_audit_logs
            ALTER COLUMN action TYPE VARCHAR(50);
            """
        )
        
        print("    ✓ Fixed tenant_audit_logs schema")

    def down(self, adapter):
        """Rollback the migration."""
        # Note: This is a destructive migration, rollback is complex
        # We'll just rename back tenant_id to tenant_uuid
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'tenant_audit_logs' 
                    AND column_name = 'tenant_id'
                ) THEN
                    ALTER TABLE tenant_audit_logs
                    RENAME COLUMN tenant_id TO tenant_uuid;
                END IF;
            END $$;
            """
        )
        print("    ✓ Rolled back tenant_audit_logs schema changes")
