from infrastructure.databases.core.base_seeder import BaseSeeder


class MetricsDefaultDefinitionsSeeder(BaseSeeder):
    """Seed default metric definitions for metrics_db."""
    
    database = 'metrics_db'  # Target database
    
    def run(self, adapter):
        """Run the seeder."""
        # Insert default metric definitions
        adapter.execute("""
            INSERT INTO metric_definitions (name, description, unit, metric_type, aggregation_method)
            VALUES
            ('api_request_count', 'Total number of API requests', 'requests', 'counter', 'sum'),
            ('api_response_time', 'API response time in milliseconds', 'ms', 'gauge', 'avg'),
            ('api_error_rate', 'API error rate percentage', 'percent', 'gauge', 'avg'),
            ('asr_processing_time', 'ASR service processing time', 'ms', 'gauge', 'avg'),
            ('tts_processing_time', 'TTS service processing time', 'ms', 'gauge', 'avg'),
            ('nmt_processing_time', 'NMT service processing time', 'ms', 'gauge', 'avg'),
            ('llm_processing_time', 'LLM service processing time', 'ms', 'gauge', 'avg'),
            ('ocr_processing_time', 'OCR service processing time', 'ms', 'gauge', 'avg'),
            ('ner_processing_time', 'NER service processing time', 'ms', 'gauge', 'avg'),
            ('cpu_usage', 'CPU usage percentage', 'percent', 'gauge', 'avg'),
            ('memory_usage', 'Memory usage percentage', 'percent', 'gauge', 'avg'),
            ('disk_usage', 'Disk usage percentage', 'percent', 'gauge', 'avg'),
            ('active_connections', 'Number of active connections', 'connections', 'gauge', 'avg'),
            ('queue_size', 'Message queue size', 'messages', 'gauge', 'avg'),
            ('cache_hit_rate', 'Cache hit rate percentage', 'percent', 'gauge', 'avg')
            ON CONFLICT (name) DO NOTHING;
        """)
        print("    ✓ Inserted 15 default metric definitions")
