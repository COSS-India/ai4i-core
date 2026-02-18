"""
Cache Warmup Seeder
Seeds Redis with initial cache data
"""
from infrastructure.databases.core.base_seeder import BaseSeeder
import json


class CacheWarmupSeeder(BaseSeeder):
    """Warm up Redis cache with frequently accessed data"""
    
    def run(self, adapter):
        """Run seeder"""
        # Set frequently accessed configuration
        config_data = {
            'app:name': 'AI4I Core Platform',
            'app:version': '1.0.0',
            'app:environment': 'development',
            'features:asr:enabled': 'true',
            'features:tts:enabled': 'true',
            'features:nmt:enabled': 'true',
        }
        
        for key, value in config_data.items():
            adapter.set(f'ai4i:cache:{key}', value, ex=86400)  # 24-hour TTL
        
        print(f"    ✓ Seeded {len(config_data)} configuration cache keys")
        
        # Set sample user sessions (for demonstration)
        sample_sessions = [
            ('user:1:session', {'user_id': '1', 'username': 'admin', 'role': 'admin'}),
            ('user:2:session', {'user_id': '2', 'username': 'user1', 'role': 'user'}),
        ]
        
        for key, data in sample_sessions:
            adapter.set(f'ai4i:session:{key}', json.dumps(data), ex=7200)  # 2-hour TTL
        
        print(f"    ✓ Seeded {len(sample_sessions)} session cache entries")
        
        # Initialize rate limit counters
        adapter.set('ai4i:ratelimit:global', '0', ex=60)
        
        print("    ✓ Initialized rate limit counters")
