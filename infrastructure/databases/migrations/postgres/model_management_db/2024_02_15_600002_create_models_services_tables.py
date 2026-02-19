from infrastructure.databases.core.base_migration import BaseMigration

class CreateModelsServicesTables(BaseMigration):
    """Create models and services tables in model_management_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create models table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                model_id VARCHAR(255) NOT NULL,
                version VARCHAR(100) NOT NULL,
                version_status version_status NOT NULL DEFAULT 'ACTIVE',
                version_status_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                submitted_on BIGINT NOT NULL,
                updated_on BIGINT,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                ref_url VARCHAR(500),
                task JSONB NOT NULL,
                languages JSONB NOT NULL DEFAULT '[]'::jsonb,
                license VARCHAR(255),
                domain JSONB NOT NULL DEFAULT '[]'::jsonb,
                inference_endpoint JSONB NOT NULL,
                benchmarks JSONB,
                submitter JSONB NOT NULL,
                created_by VARCHAR(255) DEFAULT NULL,
                updated_by VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_name_version UNIQUE (name, version)
            );
        """)
        print("    ✓ Created models table")

        # Create services table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                service_id VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                service_description TEXT,
                hardware_description TEXT,
                published_on BIGINT NOT NULL,
                model_id VARCHAR(255) NOT NULL,
                model_version VARCHAR(100) NOT NULL,
                endpoint VARCHAR(500) NOT NULL,
                api_key VARCHAR(255),
                health_status JSONB,
                benchmarks JSONB,
                policy JSONB,
                is_published BOOLEAN NOT NULL DEFAULT FALSE,
                published_at BIGINT DEFAULT NULL,
                unpublished_at BIGINT DEFAULT NULL,
                created_by VARCHAR(255) DEFAULT NULL,
                updated_by VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_model_id_version_service_name UNIQUE (model_id, model_version, name)
            );
        """)
        print("    ✓ Created services table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS services CASCADE;
            DROP TABLE IF EXISTS models CASCADE;
        """)
        print("    ✓ Dropped models and services tables")
