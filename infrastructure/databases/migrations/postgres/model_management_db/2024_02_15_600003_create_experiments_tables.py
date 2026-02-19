from infrastructure.databases.core.base_migration import BaseMigration

class CreateExperimentsTables(BaseMigration):
    """Create A/B testing tables (experiments, experiment_variants, experiment_metrics) in model_management_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create experiments table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                description TEXT,
                status experiment_status NOT NULL DEFAULT 'DRAFT',
                task_type JSONB DEFAULT NULL,
                languages JSONB DEFAULT NULL,
                start_date TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                end_date TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                created_by VARCHAR(255) DEFAULT NULL,
                updated_by VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                completed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
            );
        """)
        print("    ✓ Created experiments table")

        # Create experiment_variants table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS experiment_variants (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                variant_name VARCHAR(255) NOT NULL,
                service_id VARCHAR(255) NOT NULL REFERENCES services(service_id) ON DELETE CASCADE,
                traffic_percentage BIGINT NOT NULL,
                description TEXT DEFAULT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_experiment_service UNIQUE (experiment_id, service_id)
            );
        """)
        print("    ✓ Created experiment_variants table")

        # Create experiment_metrics table
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS experiment_metrics (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                variant_id UUID NOT NULL REFERENCES experiment_variants(id) ON DELETE CASCADE,
                request_count BIGINT NOT NULL DEFAULT 0,
                success_count BIGINT NOT NULL DEFAULT 0,
                error_count BIGINT NOT NULL DEFAULT 0,
                avg_latency_ms BIGINT DEFAULT NULL,
                custom_metrics JSONB DEFAULT NULL,
                metric_date TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_experiment_variant_date UNIQUE (experiment_id, variant_id, metric_date)
            );
        """)
        print("    ✓ Created experiment_metrics table")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TABLE IF EXISTS experiment_metrics CASCADE;
            DROP TABLE IF EXISTS experiment_variants CASCADE;
            DROP TABLE IF EXISTS experiments CASCADE;
        """)
        print("    ✓ Dropped experiment tables")
