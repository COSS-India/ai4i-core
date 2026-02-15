"""
Base Migration Class
All database migrations inherit from this base class
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseMigration(ABC):
    """Base class for all database migrations"""
    
    def __init__(self):
        self.description = self.__doc__ or "No description provided"
        self.batch = 1
        
    @abstractmethod
    def up(self, adapter: Any) -> None:
        """
        Run the migration
        
        Args:
            adapter: Database adapter instance
        """
        pass
    
    @abstractmethod
    def down(self, adapter: Any) -> None:
        """
        Rollback the migration
        
        Args:
            adapter: Database adapter instance
        """
        pass
    
    def get_name(self) -> str:
        """Get migration class name"""
        return self.__class__.__name__
