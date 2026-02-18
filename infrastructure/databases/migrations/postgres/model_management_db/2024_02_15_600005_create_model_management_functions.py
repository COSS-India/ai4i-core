from infrastructure.databases.core.base_migration import BaseMigration

class CreateModelManagementFunctions(BaseMigration):
    """Create functions and triggers for model management in model_management_db."""

    def up(self, adapter):
        """Run the migration."""
        # Create updated_at trigger function
        adapter.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        print("    ✓ Created update_updated_at_column function")

        # Create trigger for version_status_updated_at
        adapter.execute("""
            CREATE OR REPLACE FUNCTION update_version_status_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.version_status IS DISTINCT FROM OLD.version_status THEN
                    NEW.version_status_updated_at = CURRENT_TIMESTAMP;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created update_version_status_updated_at function")

        # Create triggers for updated_at columns
        adapter.execute("""
            DROP TRIGGER IF EXISTS update_models_version_status_updated_at ON models;
            CREATE TRIGGER update_models_version_status_updated_at
                BEFORE UPDATE ON models
                FOR EACH ROW
                WHEN (NEW.version_status IS DISTINCT FROM OLD.version_status)
                EXECUTE FUNCTION update_version_status_updated_at();

            DROP TRIGGER IF EXISTS update_models_updated_at ON models;
            CREATE TRIGGER update_models_updated_at 
                BEFORE UPDATE ON models
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            DROP TRIGGER IF EXISTS update_services_updated_at ON services;
            CREATE TRIGGER update_services_updated_at 
                BEFORE UPDATE ON services
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            DROP TRIGGER IF EXISTS update_experiments_updated_at ON experiments;
            CREATE TRIGGER update_experiments_updated_at 
                BEFORE UPDATE ON experiments
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            DROP TRIGGER IF EXISTS update_experiment_variants_updated_at ON experiment_variants;
            CREATE TRIGGER update_experiment_variants_updated_at 
                BEFORE UPDATE ON experiment_variants
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            DROP TRIGGER IF EXISTS update_experiment_metrics_updated_at ON experiment_metrics;
            CREATE TRIGGER update_experiment_metrics_updated_at 
                BEFORE UPDATE ON experiment_metrics
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
        print("    ✓ Created updated_at triggers")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP TRIGGER IF EXISTS update_experiment_metrics_updated_at ON experiment_metrics;
            DROP TRIGGER IF EXISTS update_experiment_variants_updated_at ON experiment_variants;
            DROP TRIGGER IF EXISTS update_experiments_updated_at ON experiments;
            DROP TRIGGER IF EXISTS update_services_updated_at ON services;
            DROP TRIGGER IF EXISTS update_models_updated_at ON models;
            DROP TRIGGER IF EXISTS update_models_version_status_updated_at ON models;
            DROP FUNCTION IF EXISTS update_version_status_updated_at CASCADE;
            DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;
        """)
        print("    ✓ Dropped model management functions and triggers")
