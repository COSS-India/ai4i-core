from infrastructure.databases.core.base_seeder import BaseSeeder

class AlertingDefaultRulesSeeder(BaseSeeder):
    """Seed default alert rules for common monitoring scenarios in alerting_db."""
    
    database = 'alerting_db'  # Target database
    
    def run(self, adapter):
        """Run the seeder."""
        # Insert default alert rules
        adapter.execute("""
            INSERT INTO alert_rules (name, description, metric_name, threshold, operator, severity, evaluation_window, notification_channels, is_active, created_by)
            VALUES
            ('High API Latency', 'Alert when API response time exceeds 2 seconds', 'api_response_time', 2000, 'gt', 'warning', 300, ARRAY['email', 'slack'], true, 'system'),
            ('Critical API Latency', 'Critical alert when API response time exceeds 5 seconds', 'api_response_time', 5000, 'gt', 'critical', 180, ARRAY['email', 'slack', 'sms'], true, 'system'),
            ('High Error Rate', 'Alert when error rate exceeds 5%', 'error_rate', 5.0, 'gt', 'warning', 300, ARRAY['email', 'slack'], true, 'system'),
            ('Critical Error Rate', 'Critical alert when error rate exceeds 10%', 'error_rate', 10.0, 'gt', 'critical', 180, ARRAY['email', 'slack', 'sms'], true, 'system'),
            ('High CPU Usage', 'Alert when CPU usage exceeds 80%', 'cpu_usage', 80.0, 'gt', 'warning', 600, ARRAY['email'], true, 'system'),
            ('Critical CPU Usage', 'Critical alert when CPU usage exceeds 95%', 'cpu_usage', 95.0, 'gt', 'critical', 300, ARRAY['email', 'slack'], true, 'system'),
            ('High Memory Usage', 'Alert when memory usage exceeds 85%', 'memory_usage', 85.0, 'gt', 'warning', 600, ARRAY['email'], true, 'system'),
            ('Low Disk Space', 'Alert when disk space falls below 20%', 'disk_space_available', 20.0, 'lt', 'warning', 1800, ARRAY['email'], true, 'system'),
            ('Critical Disk Space', 'Critical alert when disk space falls below 10%', 'disk_space_available', 10.0, 'lt', 'critical', 600, ARRAY['email', 'slack'], true, 'system'),
            ('Service Down', 'Alert when service health check fails', 'service_health', 0, 'eq', 'critical', 60, ARRAY['email', 'slack', 'sms'], true, 'system')
            ON CONFLICT (name) DO NOTHING;
        """)
        print("    ✓ Inserted 10 default alert rules")

        # Insert sample escalation policy
        adapter.execute("""
            INSERT INTO escalation_policies (name, rules, schedule)
            VALUES
            (
                'Default Escalation Policy',
                '{"levels": [{"timeout": "5m", "notify": ["on-call-primary"]}, {"timeout": "15m", "notify": ["on-call-secondary"]}, {"timeout": "30m", "notify": ["team-lead"]}]}'::jsonb,
                '{"business_hours": {"start": "09:00", "end": "18:00", "timezone": "UTC", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]}}'::jsonb
            )
            ON CONFLICT (name) DO NOTHING;
        """)
        print("    ✓ Inserted default escalation policy")
