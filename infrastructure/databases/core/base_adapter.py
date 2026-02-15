"""
Base Database Adapter
Abstract base class that all database adapters must implement
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseAdapter(ABC):
    """Base class for all database adapters"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize adapter with configuration
        
        Args:
            config: Database connection configuration
        """
        self.config = config
        self.connection = None
        
    @abstractmethod
    def connect(self) -> None:
        """Establish database connection"""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection"""
        pass
    
    @abstractmethod
    def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Execute a database query/command
        
        Args:
            query: Query or command to execute
            params: Optional parameters for the query
            
        Returns:
            Query result
        """
        pass
    
    @abstractmethod
    def create_migrations_table(self) -> None:
        """Create migrations tracking table/structure"""
        pass
    
    @abstractmethod
    def get_executed_migrations(self) -> List[str]:
        """
        Get list of already executed migrations
        
        Returns:
            List of migration names
        """
        pass
    
    @abstractmethod
    def record_migration(self, migration_name: str, batch: int) -> None:
        """
        Record a migration as executed
        
        Args:
            migration_name: Name of the migration
            batch: Batch number
        """
        pass
    
    @abstractmethod
    def remove_migration(self, migration_name: str) -> None:
        """
        Remove a migration record (for rollback)
        
        Args:
            migration_name: Name of the migration
        """
        pass
    
    @abstractmethod
    def get_last_batch_number(self) -> int:
        """
        Get the last batch number
        
        Returns:
            Last batch number
        """
        pass
    
    @abstractmethod
    def get_migrations_by_batch(self, batch: int) -> List[str]:
        """
        Get migrations from a specific batch
        
        Args:
            batch: Batch number
            
        Returns:
            List of migration names
        """
        pass
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
