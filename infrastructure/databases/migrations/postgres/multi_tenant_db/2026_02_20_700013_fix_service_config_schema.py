from infrastructure.databases.core.base_migration import BaseMigration


class FixServiceConfigSchema(BaseMigration):
    """
    Fix service_config table to match model: change id from UUID to BigInteger, remove unused columns.
    
    ⚠️ CRITICAL: This migration must run BEFORE 700014 (fix_user_billing_records_schema) 
    because user_billing_records.service_id references service_config.id.
    
    ⚠️ WARNING: If service_config has existing data, UUID IDs will be replaced with sequential BIGINT IDs.
    Any external references to old UUID IDs will be broken.
    """

    def up(self, adapter):
        """Run the migration."""
        # Step 1: Remove unused columns (if they exist)
        adapter.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'service_config' 
                    AND column_name = 'display_name'
                ) THEN
                    ALTER TABLE service_config DROP COLUMN display_name;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'service_config' 
                    AND column_name = 'description'
                ) THEN
                    ALTER TABLE service_config DROP COLUMN description;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'service_config' 
                    AND column_name = 'base_price'
                ) THEN
                    ALTER TABLE service_config DROP COLUMN base_price;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'service_config' 
                    AND column_name = 'pricing_model'
                ) THEN
                    ALTER TABLE service_config DROP COLUMN pricing_model;
                END IF;
                
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'service_config' 
                    AND column_name = 'features'
                ) THEN
                    ALTER TABLE service_config DROP COLUMN features;
                END IF;
            END $$;
            """
        )
        
        # Step 2: Change id from UUID to BIGSERIAL (BigInteger with auto-increment)
        # This is complex - we need to create a new sequence and update the column
        adapter.execute(
            """
            DO $$
            DECLARE
                row_count BIGINT;
                seq_name TEXT;
            BEGIN
                -- Check if id is UUID type
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'service_config' 
                    AND column_name = 'id'
                    AND data_type = 'uuid'
                ) THEN
                    -- Get row count
                    SELECT COUNT(*) INTO row_count FROM service_config;
                    
                    -- If table has data, we need to preserve it
                    IF row_count > 0 THEN
                        -- Create sequence starting from row_count + 1
                        seq_name := 'service_config_id_seq';
                        EXECUTE format('DROP SEQUENCE IF EXISTS %I', seq_name);
                        EXECUTE format('CREATE SEQUENCE %I START %s', seq_name, row_count + 1);
                        
                        -- Add new bigint column
                        ALTER TABLE service_config ADD COLUMN id_new BIGINT;
                        
                        -- Populate with sequential IDs (assign new IDs to each row)
                        -- Note: This loses the original UUID mapping, but creates new sequential IDs
                        EXECUTE format('UPDATE service_config SET id_new = nextval(''%I'')', seq_name);
                        
                        -- Drop old column and constraints (CASCADE will drop foreign keys)
                        ALTER TABLE service_config DROP CONSTRAINT IF EXISTS service_config_pkey CASCADE;
                        ALTER TABLE service_config DROP COLUMN id CASCADE;
                        
                        -- Rename new column
                        ALTER TABLE service_config RENAME COLUMN id_new TO id;
                        
                        -- Set NOT NULL and add primary key
                        ALTER TABLE service_config ALTER COLUMN id SET NOT NULL;
                        ALTER TABLE service_config ADD PRIMARY KEY (id);
                        
                        -- Set sequence to use the new column and make it default
                        EXECUTE format('ALTER SEQUENCE %I OWNED BY service_config.id', seq_name);
                        ALTER TABLE service_config ALTER COLUMN id SET DEFAULT nextval(seq_name::regclass);
                    ELSE
                        -- Table is empty, simpler conversion
                        ALTER TABLE service_config DROP CONSTRAINT IF EXISTS service_config_pkey;
                        ALTER TABLE service_config DROP COLUMN id;
                        ALTER TABLE service_config ADD COLUMN id BIGSERIAL PRIMARY KEY;
                    END IF;
                END IF;
            END $$;
            """
        )
        
        # Step 3: Update service_name length to match model (VARCHAR(50))
        adapter.execute(
            """
            ALTER TABLE service_config
            ALTER COLUMN service_name TYPE VARCHAR(50);
            """
        )
        
        print("    ✓ Fixed service_config schema")

    def down(self, adapter):
        """Rollback the migration."""
        # Note: This is a destructive migration, rollback is complex
        # We'll just note that rollback would require restoring UUID type
        print("    ⚠ Rollback of service_config id type change is complex and not implemented")
