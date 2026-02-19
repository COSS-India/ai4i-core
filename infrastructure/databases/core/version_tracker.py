"""
Migration Version Tracker
Handles tracking of migration versions across all databases
"""
from datetime import datetime
from typing import Dict, List, Optional


class VersionTracker:
    """Track migration versions across all databases"""
    
    def __init__(self, adapter):
        """
        Initialize version tracker
        
        Args:
            adapter: Database adapter instance
        """
        self.adapter = adapter
        
    def ensure_tracking_table(self) -> None:
        """Ensure migrations tracking table exists"""
        self.adapter.create_migrations_table()
        
    def get_executed_migrations(self) -> List[str]:
        """
        Get list of executed migrations
        
        Returns:
            List of migration names
        """
        return self.adapter.get_executed_migrations()
        
    def record_migration(self, migration_name: str, batch: int) -> None:
        """
        Record a migration as executed
        
        Args:
            migration_name: Name of the migration
            batch: Batch number
        """
        self.adapter.record_migration(migration_name, batch)
        
    def remove_migration(self, migration_name: str) -> None:
        """
        Remove a migration record
        
        Args:
            migration_name: Name of the migration
        """
        self.adapter.remove_migration(migration_name)
        
    def get_next_batch_number(self) -> int:
        """
        Get next batch number
        
        Returns:
            Next batch number
        """
        return self.adapter.get_last_batch_number() + 1
        
    def get_last_batch_migrations(self) -> List[str]:
        """
        Get migrations from the last batch
        
        Returns:
            List of migration names
        """
        last_batch = self.adapter.get_last_batch_number()
        if last_batch == 0:
            return []
        return self.adapter.get_migrations_by_batch(last_batch)
