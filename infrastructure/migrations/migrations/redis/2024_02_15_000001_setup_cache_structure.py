"""
Setup Cache and Session Structure Migration
Production Redis cache, session, and rate limiting configuration for AI4I Core
"""
from infrastructure.migrations.core.base_migration import BaseMigration


class SetupCacheStructure(BaseMigration):
    """Setup Redis cache, session, and rate limiting structure for production use"""
    
    def up(self, adapter):
        """Run migration"""
        # Cache configuration
        adapter.set('ai4i:config:cache:prefix', 'ai4i:cache:')
        adapter.set('ai4i:config:cache:default_ttl', '3600')  # 1 hour
        adapter.set('ai4i:config:cache:model_ttl', '86400')  # 24 hours for model metadata
        adapter.set('ai4i:config:cache:enabled', 'true')
        print("    ✓ Configured cache settings")
        
        # Session configuration
        adapter.set('ai4i:config:session:prefix', 'ai4i:session:')
        adapter.set('ai4i:config:session:ttl', '7200')  # 2 hours
        adapter.set('ai4i:config:session:refresh_ttl', '604800')  # 7 days
        print("    ✓ Configured session settings")
        
        # Rate limiting configuration by service
        rate_limits = {
            'asr-service': '1000',
            'tts-service': '1000',
            'nmt-service': '2000',
            'llm-service': '500',
            'ocr-service': '500',
            'ner-service': '1000',
            'auth-service': '100',
            'api-gateway': '5000'
        }
        
        for service, limit in rate_limits.items():
            adapter.set(f'ai4i:config:ratelimit:{service}:window', '60')  # 1 minute window
            adapter.set(f'ai4i:config:ratelimit:{service}:max_requests', limit)
        print(f"    ✓ Configured rate limits for {len(rate_limits)} services")
        
        # Initialize statistics tracking
        adapter.hset('ai4i:stats:cache', 'hits', '0')
        adapter.hset('ai4i:stats:cache', 'misses', '0')
        adapter.hset('ai4i:stats:cache', 'total_keys', '0')
        adapter.hset('ai4i:stats:cache', 'evictions', '0')
        
        adapter.hset('ai4i:stats:sessions', 'active', '0')
        adapter.hset('ai4i:stats:sessions', 'total_created', '0')
        adapter.hset('ai4i:stats:sessions', 'expired', '0')
        print("    ✓ Initialized statistics counters")
        
        # Feature flags cache (synced from config-service)
        adapter.set('ai4i:feature_flags:sync_interval', '300')  # 5 minutes
        print("    ✓ Configured feature flags sync")
    
    def down(self, adapter):
        """Rollback migration"""
        # Delete all configuration keys
        keys_to_delete = [
            'ai4i:config:cache:prefix',
            'ai4i:config:cache:default_ttl',
            'ai4i:config:cache:model_ttl',
            'ai4i:config:cache:enabled',
            'ai4i:config:session:prefix',
            'ai4i:config:session:ttl',
            'ai4i:config:session:refresh_ttl',
            'ai4i:feature_flags:sync_interval'
        ]
        
        # Delete rate limit configs for all services
        services = ['asr-service', 'tts-service', 'nmt-service', 'llm-service', 
                   'ocr-service', 'ner-service', 'auth-service', 'api-gateway']
        for service in services:
            keys_to_delete.append(f'ai4i:config:ratelimit:{service}:window')
            keys_to_delete.append(f'ai4i:config:ratelimit:{service}:max_requests')
        
        adapter.delete(*keys_to_delete)
        
        # Delete stats
        adapter.delete('ai4i:stats:cache', 'ai4i:stats:sessions')
        
        print("    ✓ Removed all configuration keys and stats")
