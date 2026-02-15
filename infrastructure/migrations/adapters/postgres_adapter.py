"""
PostgreSQL Database Adapter
Handles PostgreSQL-specific migration operations
"""
import asyncio
from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker

from infrastructure.migrations.core.base_adapter import BaseAdapter


class PostgresAdapter(BaseAdapter):
    """PostgreSQL database adapter"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize PostgreSQL adapter
        
        Args:
            config: Database configuration with keys:
                - host: Database host
                - port: Database port
                - user: Database user
                - password: Database password
                - database: Database name
        """
        super().__init__(config)
        self.engine = None
        self.connection = None
        self._is_async = config.get('async', False)
        
    def connect(self) -> None:
        """Establish database connection"""
        if self._is_async:
            # Async connection
            database_url = (
                f"postgresql+asyncpg://{self.config['user']}:{self.config['password']}"
                f"@{self.config['host']}:{self.config['port']}/{self.config['database']}"
            )
            self.engine = create_async_engine(database_url, echo=False)
            # Run async connection in event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.connection = loop.run_until_complete(self.engine.connect())
            self._loop = loop
        else:
            # Sync connection
            database_url = (
                f"postgresql://{self.config['user']}:{self.config['password']}"
                f"@{self.config['host']}:{self.config['port']}/{self.config['database']}"
            )
            self.engine = create_engine(database_url, echo=False)
            self.connection = self.engine.connect()
    
    def disconnect(self) -> None:
        """Close database connection"""
        if self.connection:
            if self._is_async:
                self._loop.run_until_complete(self.connection.close())
                self._loop.run_until_complete(self.engine.dispose())
                self._loop.close()
            else:
                self.connection.close()
                self.engine.dispose()
    
    def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Execute a SQL query
        
        Args:
            query: SQL query to execute
            params: Optional query parameters
            
        Returns:
            Query result
        """
        if self._is_async:
            return self._loop.run_until_complete(
                self.connection.execute(text(query), params or {})
            )
        else:
            result = self.connection.execute(text(query), params or {})
            self.connection.commit()
            return result
    
    def create_migrations_table(self) -> None:
        """Create migrations tracking table"""
        query = """
        CREATE TABLE IF NOT EXISTS migrations (
            id SERIAL PRIMARY KEY,
            migration VARCHAR(255) NOT NULL UNIQUE,
            batch INTEGER NOT NULL,
            executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.execute(query)
    
    def get_executed_migrations(self) -> List[str]:
        """Get list of executed migrations"""
        try:
            query = "SELECT migration FROM migrations ORDER BY id"
            result = self.execute(query)
            
            if self._is_async:
                rows = self._loop.run_until_complete(result.fetchall())
            else:
                rows = result.fetchall()
            
            return [row[0] for row in rows]
        except Exception:
            # Table doesn't exist yet
            return []
    
    def record_migration(self, migration_name: str, batch: int) -> None:
        """Record a migration as executed"""
        query = """
        INSERT INTO migrations (migration, batch) 
        VALUES (:migration, :batch)
        """
        self.execute(query, {'migration': migration_name, 'batch': batch})
    
    def remove_migration(self, migration_name: str) -> None:
        """Remove a migration record"""
        query = "DELETE FROM migrations WHERE migration = :migration"
        self.execute(query, {'migration': migration_name})
    
    def get_last_batch_number(self) -> int:
        """Get the last batch number"""
        try:
            query = "SELECT COALESCE(MAX(batch), 0) as last_batch FROM migrations"
            result = self.execute(query)
            
            if self._is_async:
                row = self._loop.run_until_complete(result.fetchone())
            else:
                row = result.fetchone()
            
            return row[0] if row else 0
        except Exception:
            return 0
    
    def get_migrations_by_batch(self, batch: int) -> List[str]:
        """Get migrations from a specific batch"""
        query = "SELECT migration FROM migrations WHERE batch = :batch ORDER BY id"
        result = self.execute(query, {'batch': batch})
        
        if self._is_async:
            rows = self._loop.run_until_complete(result.fetchall())
        else:
            rows = result.fetchall()
        
        return [row[0] for row in rows]
    
    def fetch_one(self, query: str, params: Optional[Dict] = None) -> Optional[tuple]:
        """
        Fetch single row
        
        Args:
            query: SQL query
            params: Optional parameters
            
        Returns:
            Single row or None
        """
        result = self.execute(query, params)
        
        if self._is_async:
            return self._loop.run_until_complete(result.fetchone())
        else:
            return result.fetchone()
    
    def fetch_all(self, query: str, params: Optional[Dict] = None) -> List[tuple]:
        """
        Fetch all rows
        
        Args:
            query: SQL query
            params: Optional parameters
            
        Returns:
            List of rows
        """
        result = self.execute(query, params)
        
        if self._is_async:
            return self._loop.run_until_complete(result.fetchall())
        else:
            return result.fetchall()
