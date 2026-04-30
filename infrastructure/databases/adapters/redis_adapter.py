"""
Redis Database Adapter
Handles Redis-specific migration operations
"""
import json
from typing import Any, Dict, List, Optional
import redis

from infrastructure.databases.core.base_adapter import BaseAdapter


class RedisAdapter(BaseAdapter):
    """Redis database adapter"""
    
    MIGRATIONS_KEY = "migrations:executed"
    MIGRATIONS_BATCH_KEY = "migrations:batch"
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Redis adapter
        
        Args:
            config: Database configuration with keys:
                - host: Redis host
                - port: Redis port
                - password: Redis password (optional)
                - db: Redis database number
        """
        super().__init__(config)
        self.client = None
        
    def connect(self) -> None:
        """Establish Redis connection"""
        self.client = redis.Redis(
            host=self.config.get('host', 'localhost'),
            port=self.config.get('port', 6379),
            password=self.config.get('password'),
            db=self.config.get('db', 0),
            decode_responses=True
        )
        # Test connection
        self.client.ping()
        self.connection = self.client
    
    def disconnect(self) -> None:
        """Close Redis connection"""
        if self.client:
            self.client.close()
    
    def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Execute Redis command
        
        Args:
            query: Command name (GET, SET, HSET, etc.)
            params: Command parameters
            
        Returns:
            Command result
        """
        # Parse command
        parts = query.strip().split(None, 1)
        command = parts[0].upper()
        
        if command == 'SET':
            key = params.get('key')
            value = params.get('value')
            return self.client.set(key, value)
        elif command == 'GET':
            key = params.get('key')
            return self.client.get(key)
        elif command == 'DELETE' or command == 'DEL':
            key = params.get('key')
            return self.client.delete(key)
        elif command == 'HSET':
            key = params.get('key')
            field = params.get('field')
            value = params.get('value')
            return self.client.hset(key, field, value)
        elif command == 'HGET':
            key = params.get('key')
            field = params.get('field')
            return self.client.hget(key, field)
        else:
            raise ValueError(f"Unsupported Redis command: {command}")
    
    def create_migrations_table(self) -> None:
        """Create migrations tracking structure (Redis sorted set)"""
        # Ensure the sorted set exists (will be created on first insert)
        if not self.client.exists(self.MIGRATIONS_KEY):
            # Initialize with empty sorted set
            self.client.zadd(self.MIGRATIONS_KEY, {}, nx=True)
    
    def get_executed_migrations(self) -> List[str]:
        """Get list of executed migrations"""
        try:
            # Get all migrations from sorted set (ordered by score/timestamp)
            migrations = self.client.zrange(self.MIGRATIONS_KEY, 0, -1)
            return list(migrations) if migrations else []
        except Exception:
            return []
    
    def record_migration(self, migration_name: str, batch: int) -> None:
        """Record a migration as executed"""
        import time
        timestamp = time.time()
        
        # Add to sorted set with timestamp as score
        self.client.zadd(self.MIGRATIONS_KEY, {migration_name: timestamp})
        
        # Store batch information
        self.client.hset(self.MIGRATIONS_BATCH_KEY, migration_name, batch)
    
    def remove_migration(self, migration_name: str) -> None:
        """Remove a migration record"""
        self.client.zrem(self.MIGRATIONS_KEY, migration_name)
        self.client.hdel(self.MIGRATIONS_BATCH_KEY, migration_name)
    
    def get_last_batch_number(self) -> int:
        """Get the last batch number"""
        try:
            batches = self.client.hvals(self.MIGRATIONS_BATCH_KEY)
            if batches:
                return max(int(b) for b in batches)
            return 0
        except Exception:
            return 0
    
    def get_migrations_by_batch(self, batch: int) -> List[str]:
        """Get migrations from a specific batch"""
        migrations = []
        batch_data = self.client.hgetall(self.MIGRATIONS_BATCH_KEY)
        
        for migration, migration_batch in batch_data.items():
            if int(migration_batch) == batch:
                migrations.append(migration)
        
        return sorted(migrations)
    
    # Redis-specific helper methods
    
    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """
        Set a key-value pair
        
        Args:
            key: Redis key
            value: Value to store
            ex: Optional expiration time in seconds
            
        Returns:
            True if successful
        """
        return self.client.set(key, value, ex=ex)
    
    def get(self, key: str) -> Optional[str]:
        """
        Get value by key
        
        Args:
            key: Redis key
            
        Returns:
            Value or None
        """
        return self.client.get(key)
    
    def delete(self, *keys: str) -> int:
        """
        Delete one or more keys
        
        Args:
            keys: Keys to delete
            
        Returns:
            Number of keys deleted
        """
        return self.client.delete(*keys)
    
    def hset(self, name: str, key: str, value: Any) -> int:
        """
        Set hash field
        
        Args:
            name: Hash name
            key: Field key
            value: Field value
            
        Returns:
            1 if new field, 0 if updated
        """
        return self.client.hset(name, key, value)
    
    def hget(self, name: str, key: str) -> Optional[str]:
        """
        Get hash field value
        
        Args:
            name: Hash name
            key: Field key
            
        Returns:
            Field value or None
        """
        return self.client.hget(name, key)
    
    def expire(self, key: str, seconds: int) -> bool:
        """
        Set key expiration
        
        Args:
            key: Redis key
            seconds: Expiration time in seconds
            
        Returns:
            True if successful
        """
        return self.client.expire(key, seconds)
