"""
Create AI4I Logs Indices Migration
Production Elasticsearch indices for AI4I Core platform logging
"""
from infrastructure.migrations.core.base_migration import BaseMigration


class CreateLogsIndex(BaseMigration):
    """Create Elasticsearch indices for AI4I Core application and service logs"""
    
    def up(self, adapter):
        """Run migration"""
        # Create application logs index
        mappings = {
            "properties": {
                "timestamp": {"type": "date"},
                "level": {"type": "keyword"},
                "service": {"type": "keyword"},
                "message": {"type": "text"},
                "trace_id": {"type": "keyword"},
                "span_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "metadata": {"type": "object", "enabled": False}
            }
        }
        
        settings = {
            "number_of_shards": 3,
            "number_of_replicas": 1,
            "index.refresh_interval": "5s"
        }
        
        adapter.create_index('application-logs', mappings, settings)
        print("    ✓ Created application-logs index")
        
        # Create error logs index
        error_mappings = {
            "properties": {
                "timestamp": {"type": "date"},
                "service": {"type": "keyword"},
                "error_type": {"type": "keyword"},
                "error_message": {"type": "text"},
                "stack_trace": {"type": "text"},
                "user_id": {"type": "keyword"},
                "request_id": {"type": "keyword"}
            }
        }
        
        adapter.create_index('error-logs', error_mappings, settings)
        print("    ✓ Created error-logs index")
        
        # Create index template for time-series logs
        template_body = {
            "index_patterns": ["logs-*"],
            "template": {
                "settings": {
                    "number_of_shards": 2,
                    "number_of_replicas": 1
                },
                "mappings": {
                    "properties": {
                        "timestamp": {"type": "date"},
                        "service": {"type": "keyword"},
                        "level": {"type": "keyword"},
                        "message": {"type": "text"}
                    }
                }
            }
        }
        
        adapter.create_index_template('logs-template', template_body)
        print("    ✓ Created logs-template index template")
    
    def down(self, adapter):
        """Rollback migration"""
        adapter.delete_index('application-logs')
        adapter.delete_index('error-logs')
        adapter.delete_index_template('logs-template')
        
        print("    ✓ Deleted all log indices and templates")
