"""
Database Adapters
Implementations for different database types
"""
from .postgres_adapter import PostgresAdapter

__all__ = [
    'PostgresAdapter',
]
