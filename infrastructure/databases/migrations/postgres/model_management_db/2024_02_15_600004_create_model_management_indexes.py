from infrastructure.databases.core.base_migration import BaseMigration

class CreateModelManagementIndexes(BaseMigration):
    """Create indexes for model management tables in model_management_db."""

    def up(self, adapter):
        """Run the migration."""
        # Indexes for models table
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_models_model_id ON models(model_id);
            CREATE INDEX IF NOT EXISTS idx_models_name ON models(name);
            CREATE INDEX IF NOT EXISTS idx_models_version ON models(version);
            CREATE INDEX IF NOT EXISTS idx_models_model_id_version ON models(model_id, version);
            CREATE INDEX IF NOT EXISTS idx_models_version_status ON models(version_status);
            CREATE INDEX IF NOT EXISTS idx_models_task ON models USING GIN (task);
            CREATE INDEX IF NOT EXISTS idx_models_languages ON models USING GIN (languages);
            CREATE INDEX IF NOT EXISTS idx_models_domain ON models USING GIN (domain);
            CREATE INDEX IF NOT EXISTS idx_models_created_at ON models(created_at);
            CREATE INDEX IF NOT EXISTS idx_models_created_by ON models(created_by);
        """)
        print("    ✓ Created indexes for models")

        # Indexes for services table
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_services_service_id ON services(service_id);
            CREATE INDEX IF NOT EXISTS idx_services_name ON services(name);
            CREATE INDEX IF NOT EXISTS idx_services_model_id ON services(model_id);
            CREATE INDEX IF NOT EXISTS idx_services_model_id_version ON services(model_id, model_version);
            CREATE INDEX IF NOT EXISTS idx_services_is_published ON services(is_published);
            CREATE INDEX IF NOT EXISTS idx_services_created_at ON services(created_at);
            CREATE INDEX IF NOT EXISTS idx_services_health_status ON services USING GIN (health_status);
            CREATE INDEX IF NOT EXISTS idx_services_policy ON services USING GIN (policy);
            CREATE INDEX IF NOT EXISTS idx_services_created_by ON services(created_by);
        """)
        print("    ✓ Created indexes for services")

        # Indexes for experiments
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
            CREATE INDEX IF NOT EXISTS idx_experiments_created_at ON experiments(created_at);
            CREATE INDEX IF NOT EXISTS idx_experiments_started_at ON experiments(started_at);
            CREATE INDEX IF NOT EXISTS idx_experiments_completed_at ON experiments(completed_at);
        """)
        print("    ✓ Created indexes for experiments")

        # Indexes for experiment_variants
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_experiment_variants_experiment_id ON experiment_variants(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_experiment_variants_service_id ON experiment_variants(service_id);
        """)
        print("    ✓ Created indexes for experiment_variants")

        # Indexes for experiment_metrics
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_experiment_metrics_experiment_id ON experiment_metrics(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_experiment_metrics_variant_id ON experiment_metrics(variant_id);
            CREATE INDEX IF NOT EXISTS idx_experiment_metrics_metric_date ON experiment_metrics(metric_date);
            CREATE INDEX IF NOT EXISTS idx_experiment_metrics_exp_var_date ON experiment_metrics(experiment_id, variant_id, metric_date);
        """)
        print("    ✓ Created indexes for experiment_metrics")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_experiment_metrics_exp_var_date;
            DROP INDEX IF EXISTS idx_experiment_metrics_metric_date;
            DROP INDEX IF EXISTS idx_experiment_metrics_variant_id;
            DROP INDEX IF EXISTS idx_experiment_metrics_experiment_id;
            DROP INDEX IF EXISTS idx_experiment_variants_service_id;
            DROP INDEX IF EXISTS idx_experiment_variants_experiment_id;
            DROP INDEX IF EXISTS idx_experiments_completed_at;
            DROP INDEX IF EXISTS idx_experiments_started_at;
            DROP INDEX IF EXISTS idx_experiments_created_at;
            DROP INDEX IF EXISTS idx_experiments_status;
            DROP INDEX IF EXISTS idx_services_created_by;
            DROP INDEX IF EXISTS idx_services_policy;
            DROP INDEX IF EXISTS idx_services_health_status;
            DROP INDEX IF EXISTS idx_services_created_at;
            DROP INDEX IF EXISTS idx_services_is_published;
            DROP INDEX IF EXISTS idx_services_model_id_version;
            DROP INDEX IF EXISTS idx_services_model_id;
            DROP INDEX IF EXISTS idx_services_name;
            DROP INDEX IF EXISTS idx_services_service_id;
            DROP INDEX IF EXISTS idx_models_created_by;
            DROP INDEX IF EXISTS idx_models_created_at;
            DROP INDEX IF EXISTS idx_models_domain;
            DROP INDEX IF EXISTS idx_models_languages;
            DROP INDEX IF EXISTS idx_models_task;
            DROP INDEX IF EXISTS idx_models_version_status;
            DROP INDEX IF EXISTS idx_models_model_id_version;
            DROP INDEX IF EXISTS idx_models_version;
            DROP INDEX IF EXISTS idx_models_name;
            DROP INDEX IF EXISTS idx_models_model_id;
        """)
        print("    ✓ Dropped model management indexes")
