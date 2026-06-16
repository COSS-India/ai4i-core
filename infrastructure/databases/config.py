"""
Migration Configuration
Database connection configurations for all databases
"""
import os
from typing import Dict, Any


class MigrationConfig:
    """Configuration for database migrations"""

    @staticmethod
    def get_postgres_config(database: str = 'auth_db') -> Dict[str, Any]:
        """Get PostgreSQL configuration"""
        return {
            'host': os.getenv('POSTGRES_HOST'),
            'port': int(os.getenv('POSTGRES_PORT')),
            'user': os.getenv('POSTGRES_USER'),
            'password': os.getenv('POSTGRES_PASSWORD'),
            'database': database,
            'async': False
        }


    @staticmethod
    def get_adapter_class(database_type: str):
        """
        Get adapter class for database type

        Args:
            database_type: Type of database (postgres)

        Returns:
            Adapter class
        """
        from infrastructure.databases.adapters import PostgresAdapter

        adapters = {
            'postgres': PostgresAdapter,
        }

        if database_type not in adapters:
            raise ValueError(f"Unsupported database type: {database_type}")

        return adapters[database_type]

    @staticmethod
    def get_config_for_database(database_type: str, **kwargs) -> Dict[str, Any]:
        """
        Get configuration for specific database type

        Args:
            database_type: Type of database (postgres)
            **kwargs: Additional configuration overrides

        Returns:
            Database configuration
        """
        config_methods = {
            'postgres': MigrationConfig.get_postgres_config,
        }

        if database_type not in config_methods:
            raise ValueError(f"Unsupported database type: {database_type}")

        config = config_methods[database_type](**kwargs)
        config.update(kwargs)
        return config
