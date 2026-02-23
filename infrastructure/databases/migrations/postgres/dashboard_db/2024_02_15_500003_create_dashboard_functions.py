from infrastructure.databases.core.base_migration import BaseMigration

class CreateDashboardFunctions(BaseMigration):
    """Create functions and triggers for dashboard management in dashboard_db."""

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

        # Drop triggers if they exist (idempotent for re-runs), then create triggers for updated_at columns
        adapter.execute("""
            DROP TRIGGER IF EXISTS update_dashboards_updated_at ON dashboards;
            DROP TRIGGER IF EXISTS update_dashboard_widgets_updated_at ON dashboard_widgets;
            DROP TRIGGER IF EXISTS update_saved_queries_updated_at ON saved_queries;
            DROP TRIGGER IF EXISTS update_reports_updated_at ON reports;
            DROP TRIGGER IF EXISTS update_user_preferences_updated_at ON user_preferences;

            CREATE TRIGGER update_dashboards_updated_at
                BEFORE UPDATE ON dashboards
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_dashboard_widgets_updated_at
                BEFORE UPDATE ON dashboard_widgets
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_saved_queries_updated_at
                BEFORE UPDATE ON saved_queries
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_reports_updated_at
                BEFORE UPDATE ON reports
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

            CREATE TRIGGER update_user_preferences_updated_at
                BEFORE UPDATE ON user_preferences
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
        print("    ✓ Created updated_at triggers")

        # Create function to get dashboard with widgets (param p_id avoids conflict with output column dashboard_id)
        adapter.execute("""
            CREATE OR REPLACE FUNCTION get_dashboard_with_widgets(p_id integer)
            RETURNS TABLE (
                dashboard_id integer,
                dashboard_name varchar(255),
                dashboard_description text,
                dashboard_layout jsonb,
                is_public boolean,
                owner_id integer,
                widget_id integer,
                widget_type varchar(100),
                widget_configuration jsonb,
                widget_position jsonb
            ) AS $$
            BEGIN
                RETURN QUERY
                SELECT
                    d.id,
                    d.name,
                    d.description,
                    d.layout,
                    d.is_public,
                    d.owner_id,
                    w.id,
                    w.widget_type,
                    w.configuration,
                    w.position
                FROM dashboards d
                LEFT JOIN dashboard_widgets w ON d.id = w.dashboard_id
                WHERE d.id = p_id
                ORDER BY w.id;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created get_dashboard_with_widgets function")

        # Create function to clean up old dashboard data
        adapter.execute("""
            CREATE OR REPLACE FUNCTION cleanup_old_dashboard_data(retention_days integer DEFAULT 365)
            RETURNS void AS $$
            BEGIN
                DELETE FROM reports 
                WHERE last_generated_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days
                OR (last_generated_at IS NULL AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days);
                
                DELETE FROM saved_queries 
                WHERE id NOT IN (SELECT DISTINCT query_id FROM reports WHERE query_id IS NOT NULL)
                AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("    ✓ Created cleanup_old_dashboard_data function")

    def down(self, adapter):
        """Rollback the migration."""
        adapter.execute("""
            DROP FUNCTION IF EXISTS cleanup_old_dashboard_data CASCADE;
            DROP FUNCTION IF EXISTS get_dashboard_with_widgets CASCADE;
            DROP TRIGGER IF EXISTS update_user_preferences_updated_at ON user_preferences;
            DROP TRIGGER IF EXISTS update_reports_updated_at ON reports;
            DROP TRIGGER IF EXISTS update_saved_queries_updated_at ON saved_queries;
            DROP TRIGGER IF EXISTS update_dashboard_widgets_updated_at ON dashboard_widgets;
            DROP TRIGGER IF EXISTS update_dashboards_updated_at ON dashboards;
            DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;
        """)
        print("    ✓ Dropped dashboard functions and triggers")
