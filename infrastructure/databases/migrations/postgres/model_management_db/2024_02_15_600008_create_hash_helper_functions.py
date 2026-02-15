"""
Create Hash Helper Functions for Model and Service IDs
Creates SQL functions to generate hash-based IDs for models and services
"""
from infrastructure.databases.core.base_migration import BaseMigration


class CreateHashHelperFunctions(BaseMigration):
    """Create helper functions for generating model_id and service_id hashes."""
    
    def up(self, adapter):
        """Run the migration."""
        # Create generate_model_id function
        adapter.execute("""
            -- Helper function to generate model_id hash (matches Python implementation)
            CREATE OR REPLACE FUNCTION generate_model_id(model_name TEXT, version TEXT) 
            RETURNS VARCHAR(32) AS $$
            BEGIN
                RETURN SUBSTRING(encode(sha256((LOWER(TRIM(model_name)) || ':' || LOWER(TRIM(version)))::bytea), 'hex'), 1, 32);
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
        """)
        print("    ✓ Created generate_model_id() function")
        
        # Create generate_service_id function
        adapter.execute("""
            -- Helper function to generate service_id hash (matches Python implementation)
            CREATE OR REPLACE FUNCTION generate_service_id(model_name TEXT, model_version TEXT, service_name TEXT) 
            RETURNS VARCHAR(32) AS $$
            BEGIN
                RETURN SUBSTRING(encode(sha256((LOWER(TRIM(model_name)) || ':' || LOWER(TRIM(model_version)) || ':' || LOWER(TRIM(service_name)))::bytea), 'hex'), 1, 32);
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
        """)
        print("    ✓ Created generate_service_id() function")
        
        # Add comments
        adapter.execute("""
            COMMENT ON FUNCTION generate_model_id(TEXT, TEXT) IS 
                'Generates a SHA256-based hash ID for a model from its name and version';
            
            COMMENT ON FUNCTION generate_service_id(TEXT, TEXT, TEXT) IS 
                'Generates a SHA256-based hash ID for a service from model name, model version, and service name';
        """)
        print("    ✓ Added function documentation")
    
    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP FUNCTION IF EXISTS generate_service_id(TEXT, TEXT, TEXT);
            DROP FUNCTION IF EXISTS generate_model_id(TEXT, TEXT);
        """)
        print("    ✓ Dropped hash helper functions")
