"""
Create AI4I Event Topics Migration
Production Kafka topics for AI4I Core platform events
"""
from infrastructure.databases.core.base_migration import BaseMigration


class CreateEventTopics(BaseMigration):
    """Create Kafka topics for AI4I Core system events and streaming"""
    
    def up(self, adapter):
        """Run migration"""
        # Create AI events topic
        adapter.create_topic(
            name='ai-events',
            partitions=6,
            replication_factor=1,
            configs={
                'retention.ms': str(7 * 24 * 60 * 60 * 1000),  # 7 days
                'compression.type': 'gzip'
            }
        )
        print("    ✓ Created ai-events topic (6 partitions, 7-day retention)")
        
        # Create user activity topic
        adapter.create_topic(
            name='user-activity',
            partitions=3,
            replication_factor=1,
            configs={
                'retention.ms': str(30 * 24 * 60 * 60 * 1000),  # 30 days
                'compression.type': 'snappy'
            }
        )
        print("    ✓ Created user-activity topic (3 partitions, 30-day retention)")
        
        # Create system metrics topic
        adapter.create_topic(
            name='system-metrics',
            partitions=4,
            replication_factor=1,
            configs={
                'retention.ms': str(3 * 24 * 60 * 60 * 1000),  # 3 days
                'compression.type': 'lz4'
            }
        )
        print("    ✓ Created system-metrics topic (4 partitions, 3-day retention)")
        
        # Create audit logs topic with longer retention
        adapter.create_topic(
            name='audit-logs',
            partitions=2,
            replication_factor=1,
            configs={
                'retention.ms': str(90 * 24 * 60 * 60 * 1000),  # 90 days
                'compression.type': 'gzip'
            }
        )
        print("    ✓ Created audit-logs topic (2 partitions, 90-day retention)")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.delete_topic('ai-events')
        adapter.delete_topic('user-activity')
        adapter.delete_topic('system-metrics')
        adapter.delete_topic('audit-logs')
        
        print("    ✓ Deleted all event topics")
