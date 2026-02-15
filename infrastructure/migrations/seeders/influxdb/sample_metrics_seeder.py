"""
Sample Metrics Seeder
Seeds InfluxDB with sample metrics data
"""
from infrastructure.migrations.core.base_seeder import BaseSeeder
from datetime import datetime, timedelta
import random


class SampleMetricsSeeder(BaseSeeder):
    """Seed InfluxDB with sample application metrics"""
    
    def run(self, adapter):
        """Run seeder"""
        # Generate sample metrics for the last hour
        now = datetime.utcnow()
        services = ['asr-service', 'tts-service', 'nmt-service', 'auth-service']
        
        # Seed request metrics
        for i in range(60):  # One data point per minute for the last hour
            timestamp = now - timedelta(minutes=59 - i)
            
            for service in services:
                # Request count metric
                adapter.write_point(
                    bucket='ai_metrics',
                    measurement='request_count',
                    tags={'service': service, 'status': 'success'},
                    fields={'count': random.randint(10, 100)}
                )
                
                # Response time metric
                adapter.write_point(
                    bucket='ai_metrics',
                    measurement='response_time',
                    tags={'service': service, 'endpoint': '/api/v1/inference'},
                    fields={'duration_ms': random.uniform(50, 500)}
                )
        
        print(f"    ✓ Seeded request metrics for {len(services)} services (last 60 minutes)")
        
        # Seed CPU usage metrics
        for service in services:
            adapter.write_point(
                bucket='performance_metrics',
                measurement='cpu_usage',
                tags={'service': service, 'host': 'server-01'},
                fields={'percentage': random.uniform(20, 80)}
            )
        
        print(f"    ✓ Seeded CPU usage metrics for {len(services)} services")
        
        # Seed memory usage metrics
        for service in services:
            adapter.write_point(
                bucket='performance_metrics',
                measurement='memory_usage',
                tags={'service': service, 'host': 'server-01'},
                fields={'mb': random.uniform(200, 800)}
            )
        
        print(f"    ✓ Seeded memory usage metrics for {len(services)} services")
