from infrastructure.databases.core.base_seeder import BaseSeeder

class DashboardDefaultDashboardsSeeder(BaseSeeder):
    """Seed default dashboards for system monitoring in dashboard_db."""
    
    database = 'dashboard_db'  # Target database
    
    def run(self, adapter):
        """Run the seeder."""
        # Get admin user ID from auth_db (cross-database query not supported, using default owner_id=1)
        # In production, update this after migration to use actual admin user ID
        
        # Insert default System Overview dashboard
        adapter.execute("""
            INSERT INTO dashboards (name, description, layout, is_public, owner_id)
            VALUES
            (
                'System Overview',
                'High-level system health and performance metrics',
                '{"rows": [{"widgets": [{"type": "chart", "size": "medium", "position": {"x": 0, "y": 0}}]}]}'::jsonb,
                true,
                1
            ),
            (
                'AI Services Performance',
                'Performance metrics for all AI services (ASR, TTS, NMT, LLM, OCR, NER)',
                '{"rows": [{"widgets": [{"type": "chart", "size": "large", "position": {"x": 0, "y": 0}}]}]}'::jsonb,
                true,
                1
            ),
            (
                'Infrastructure Metrics',
                'CPU, Memory, Disk, and Network metrics for all nodes',
                '{"rows": [{"widgets": [{"type": "gauge", "size": "small", "position": {"x": 0, "y": 0}}]}]}'::jsonb,
                true,
                1
            ),
            (
                'Error Analytics',
                'Error rates, types, and trends across all services',
                '{"rows": [{"widgets": [{"type": "table", "size": "large", "position": {"x": 0, "y": 0}}]}]}'::jsonb,
                true,
                1
            );
        """)
        print("    ✓ Inserted 4 default dashboards")

        # Insert sample saved queries
        adapter.execute("""
            INSERT INTO saved_queries (name, query, parameters, created_by)
            VALUES
            (
                'Top 10 Slowest API Endpoints',
                'SELECT endpoint, AVG(response_time) as avg_response, COUNT(*) as request_count FROM api_metrics WHERE timestamp > NOW() - INTERVAL ''7 days'' GROUP BY endpoint ORDER BY avg_response DESC LIMIT 10',
                '{"time_range": "7d"}'::jsonb,
                1
            ),
            (
                'Error Rate by Service',
                'SELECT service_name, SUM(error_count)::FLOAT / NULLIF(SUM(request_count), 0) * 100 as error_rate FROM api_metrics WHERE timestamp > NOW() - INTERVAL ''1 day'' GROUP BY service_name ORDER BY error_rate DESC',
                '{"time_range": "1d"}'::jsonb,
                1
            ),
            (
                'AI Service Usage Statistics',
                'SELECT service_name, COUNT(*) as total_requests, AVG(processing_time) as avg_processing_time FROM ai_service_requests WHERE created_at > NOW() - INTERVAL ''7 days'' GROUP BY service_name',
                '{"time_range": "7d"}'::jsonb,
                1
            );
        """)
        print("    ✓ Inserted 3 sample saved queries")
