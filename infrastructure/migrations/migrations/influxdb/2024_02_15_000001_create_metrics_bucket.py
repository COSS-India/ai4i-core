"""
Create AI4I Metrics Buckets Migration
Production InfluxDB buckets for AI4I Core platform metrics
"""
from infrastructure.migrations.core.base_migration import BaseMigration


class CreateMetricsBucket(BaseMigration):
    """Create InfluxDB buckets for AI4I Core metrics storage"""
    
    def up(self, adapter):
        """Run migration"""
        # AI Service Metrics (inference requests, latency, accuracy)
        adapter.create_bucket(
            bucket_name='ai_service_metrics',
            retention_days=30
        )
        print("    ✓ Created ai_service_metrics bucket (30-day retention)")
        
        # System Performance Metrics (CPU, memory, disk I/O)
        adapter.create_bucket(
            bucket_name='system_performance',
            retention_days=7
        )
        print("    ✓ Created system_performance bucket (7-day retention)")
        
        # API Gateway Metrics (request rate, response time, errors)
        adapter.create_bucket(
            bucket_name='api_gateway_metrics',
            retention_days=30
        )
        print("    ✓ Created api_gateway_metrics bucket (30-day retention)")
        
        # Business Metrics (user activity, API usage, billing)
        adapter.create_bucket(
            bucket_name='business_metrics',
            retention_days=90
        )
        print("    ✓ Created business_metrics bucket (90-day retention)")
        
        # Long-term Archive (important metrics for historical analysis)
        adapter.create_bucket(
            bucket_name='metrics_archive',
            retention_days=365
        )
        print("    ✓ Created metrics_archive bucket (365-day retention)")
        
        # Model Performance Metrics (accuracy, drift, A/B testing results)
        adapter.create_bucket(
            bucket_name='model_performance',
            retention_days=90
        )
        print("    ✓ Created model_performance bucket (90-day retention)")
    
    def down(self, adapter):
        """Rollback migration"""
        buckets = [
            'ai_service_metrics',
            'system_performance',
            'api_gateway_metrics',
            'business_metrics',
            'metrics_archive',
            'model_performance'
        ]
        
        for bucket in buckets:
            adapter.delete_bucket(bucket)
        
        print(f"    ✓ Deleted {len(buckets)} metrics buckets")
