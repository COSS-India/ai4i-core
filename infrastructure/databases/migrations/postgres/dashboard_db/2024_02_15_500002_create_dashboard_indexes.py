from infrastructure.databases.core.base_migration import BaseMigration

class CreateDashboardIndexes(BaseMigration):
    """Create indexes for dashboard tables in dashboard_db."""

    def up(self, adapter):
        """Run the migration."""
        # Indexes for dashboards
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_dashboards_owner_id ON dashboards(owner_id);
            CREATE INDEX IF NOT EXISTS idx_dashboards_is_public ON dashboards(is_public);
            CREATE INDEX IF NOT EXISTS idx_dashboards_created_at ON dashboards(created_at);
        """)
        print("    ✓ Created indexes for dashboards")

        # Indexes for dashboard_widgets
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_dashboard_id ON dashboard_widgets(dashboard_id);
            CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_widget_type ON dashboard_widgets(widget_type);
        """)
        print("    ✓ Created indexes for dashboard_widgets")

        # Indexes for saved_queries
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_saved_queries_created_by ON saved_queries(created_by);
            CREATE INDEX IF NOT EXISTS idx_saved_queries_created_at ON saved_queries(created_at);
        """)
        print("    ✓ Created indexes for saved_queries")

        # Indexes for reports
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_reports_query_id ON reports(query_id);
            CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at);
            CREATE INDEX IF NOT EXISTS idx_reports_last_generated ON reports(last_generated_at);
        """)
        print("    ✓ Created indexes for reports")

        # Indexes for user_preferences
        adapter.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);
        """)
        print("    ✓ Created indexes for user_preferences")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP INDEX IF EXISTS idx_user_preferences_user_id;
            DROP INDEX IF EXISTS idx_reports_last_generated;
            DROP INDEX IF EXISTS idx_reports_created_at;
            DROP INDEX IF EXISTS idx_reports_query_id;
            DROP INDEX IF EXISTS idx_saved_queries_created_at;
            DROP INDEX IF EXISTS idx_saved_queries_created_by;
            DROP INDEX IF EXISTS idx_dashboard_widgets_widget_type;
            DROP INDEX IF EXISTS idx_dashboard_widgets_dashboard_id;
            DROP INDEX IF EXISTS idx_dashboards_created_at;
            DROP INDEX IF EXISTS idx_dashboards_is_public;
            DROP INDEX IF EXISTS idx_dashboards_owner_id;
        """)
        print("    ✓ Dropped dashboard indexes")
