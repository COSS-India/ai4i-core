"""
Base Seeder Class
All database seeders inherit from this base class
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseSeeder(ABC):
    """Base class for all database seeders"""
    
    def __init__(self):
        self.description = self.__doc__ or "No description provided"
        
    @abstractmethod
    def run(self, adapter: Any) -> None:
        """
        Run the seeder
        
        Args:
            adapter: Database adapter instance
        """
        pass
    
    def get_name(self) -> str:
        """Get seeder class name"""
        return self.__class__.__name__
