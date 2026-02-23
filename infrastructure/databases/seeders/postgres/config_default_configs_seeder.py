"""
Default Configurations Seeder
Seeds default configuration values for config_db
Note: Use --postgres-db config_db when running this seeder
"""
from infrastructure.databases.core.base_seeder import BaseSeeder


class ConfigDefaultConfigsSeeder(BaseSeeder):
    """Seed default configurations for config_db"""
    
    database = 'config_db'  # Target database
    
    def run(self, adapter):
        """Run seeder"""
        # Insert default configurations
        configs = [
            ('api.timeout', '30', 'development', 'api-gateway-service', 'API request timeout in seconds'),
            ('cache.ttl', '300', 'development', 'api-gateway-service', 'Cache time-to-live in seconds'),
            ('rate_limit.requests_per_minute', '100', 'development', 'api-gateway-service', 'Rate limit per minute'),
            ('jwt.expiry_minutes', '15', 'development', 'auth-service', 'JWT token expiry in minutes'),
            ('jwt.refresh_expiry_days', '7', 'development', 'auth-service', 'JWT refresh token expiry in days'),
            ('metrics.retention_days', '90', 'development', 'metrics-service', 'Metrics retention period in days'),
            ('alerts.cooldown_minutes', '15', 'development', 'alerting-service', 'Alert cooldown period in minutes'),
            ('dashboard.refresh_interval', '30', 'development', 'dashboard-service', 'Dashboard refresh interval in seconds'),
        ]
        
        for key, value, environment, service_name, description in configs:
            adapter.execute(
                """
                INSERT INTO configurations (key, value, environment, service_name)
                VALUES (:key, :value, :environment, :service_name)
                ON CONFLICT (key, environment, service_name) DO NOTHING
                """,
                {
                    'key': key,
                    'value': value,
                    'environment': environment,
                    'service_name': service_name
                }
            )
        
        print(f"    ✓ Seeded {len(configs)} configurations")
        
        # Insert default feature flags
        flags = [
            ('new_dashboard_ui', 'Enable new dashboard user interface', False, '0.00', 'development'),
            ('advanced_analytics', 'Enable advanced analytics features', True, '100.00', 'development'),
            ('beta_features', 'Enable beta features for testing', False, '25.00', 'development'),
            ('api_rate_limiting', 'Enable API rate limiting', True, '100.00', 'development'),
            ('real_time_notifications', 'Enable real-time notifications', True, '50.00', 'development'),
        ]
        
        for name, description, is_enabled, rollout_percentage, environment in flags:
            adapter.execute(
                """
                INSERT INTO feature_flags (name, description, is_enabled, rollout_percentage, environment)
                VALUES (:name, :description, :is_enabled, :rollout_percentage, :environment)
                ON CONFLICT (name, environment) DO NOTHING
                """,
                {
                    'name': name,
                    'description': description,
                    'is_enabled': is_enabled,
                    'rollout_percentage': rollout_percentage,
                    'environment': environment
                }
            )
        
        print(f"    ✓ Seeded {len(flags)} feature flags")
        
        # Insert service registry entries
        services = [
            ('api-gateway-service', 'http://api-gateway-service:8080', 'http://api-gateway-service:8080/health', 'healthy'),
            ('auth-service', 'http://auth-service:8081', 'http://auth-service:8081/health', 'healthy'),
            ('config-service', 'http://config-service:8082', 'http://config-service:8082/health', 'healthy'),
            ('metrics-service', 'http://metrics-service:8083', 'http://metrics-service:8083/health', 'healthy'),
            ('telemetry-service', 'http://telemetry-service:8084', 'http://telemetry-service:8084/health', 'healthy'),
            ('alerting-service', 'http://alerting-service:8085', 'http://alerting-service:8085/health', 'healthy'),
            ('dashboard-service', 'http://dashboard-service:8086', 'http://dashboard-service:8086/health', 'healthy'),
            ('asr-service', 'http://asr-service:8001', 'http://asr-service:8001/health', 'healthy'),
            ('tts-service', 'http://tts-service:8002', 'http://tts-service:8002/health', 'healthy'),
            ('nmt-service', 'http://nmt-service:8003', 'http://nmt-service:8003/health', 'healthy'),
            ('llm-service', 'http://llm-service:8004', 'http://llm-service:8004/health', 'healthy'),
            ('ocr-service', 'http://ocr-service:8005', 'http://ocr-service:8005/health', 'healthy'),
            ('ner-service', 'http://ner-service:8006', 'http://ner-service:8006/health', 'healthy'),
        ]
        
        for service_name, service_url, health_check_url, status in services:
            adapter.execute(
                """
                INSERT INTO service_registry (service_name, service_url, health_check_url, status, service_metadata)
                VALUES (:service_name, :service_url, :health_check_url, :status, :metadata)
                ON CONFLICT (service_name) DO NOTHING
                """,
                {
                    'service_name': service_name,
                    'service_url': service_url,
                    'health_check_url': health_check_url,
                    'status': status,
                    'metadata': '{"version": "1.0.0", "environment": "development"}'
                }
            )
        
        print(f"    ✓ Seeded {len(services)} service registry entries")
