"""
Migration Configuration
Database connection configurations for all databases
"""
from typing import Dict, Any
from pathlib import Path
import sys

try:
    from ai4icore_env import app_env
except ModuleNotFoundError:
    # Fallback for local dev environments where the shared lib is not installed.
    project_root = Path(__file__).resolve().parents[2]
    candidate_paths = [
        project_root / "libs" / "ai4icore_env",
        project_root / "libs",
    ]
    for candidate in candidate_paths:
        candidate_str = str(candidate)
        if candidate.exists() and candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
    from ai4icore_env import app_env


class MigrationConfig:
    """Configuration for database migrations"""

    @staticmethod
    def get_postgres_config(database: str = 'auth_db') -> Dict[str, Any]:
        """Get PostgreSQL configuration"""
        return {
            'host': app_env.postgres_host,
            'port': app_env.postgres_port,
            'user': app_env.postgres_user,
            'password': app_env.postgres_password,
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
