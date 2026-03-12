"""
Migration Configuration
Database connection configurations for all databases
"""
from typing import Dict, Any

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
    def get_redis_config() -> Dict[str, Any]:
        """Get Redis configuration"""
        return {
            'host': app_env.redis_host,
            'port': app_env.redis_port,
            'password': app_env.redis_password,
            'db': app_env.redis_db
        }

    @staticmethod
    def get_influxdb_config() -> Dict[str, Any]:
        """Get InfluxDB configuration"""
        return {
            'url': app_env.influxdb_url,
            'token': app_env.influxdb_token,
            'org': app_env.influxdb_org,
            'bucket': app_env.influxdb_bucket
        }

    @staticmethod
    def get_elasticsearch_config() -> Dict[str, Any]:
        """Get Elasticsearch configuration"""
        return {
            'hosts': (app_env.elasticsearch_url or '').split(','),
            'username': app_env.elasticsearch_username,
            'password': app_env.elasticsearch_password,
        }

    @staticmethod
    def get_kafka_config() -> Dict[str, Any]:
        """Get Kafka configuration"""
        return {
            'bootstrap_servers': app_env.kafka_bootstrap_servers.split(','),
        }

    @staticmethod
    def get_adapter_class(database_type: str):
        """
        Get adapter class for database type

        Args:
            database_type: Type of database (postgres, redis, etc.)

        Returns:
            Adapter class
        """
        from infrastructure.databases.adapters import (
            PostgresAdapter, RedisAdapter, InfluxDBAdapter,
            ElasticsearchAdapter, KafkaAdapter
        )

        adapters = {
            'postgres': PostgresAdapter,
            'redis': RedisAdapter,
            'influxdb': InfluxDBAdapter,
            'elasticsearch': ElasticsearchAdapter,
            'kafka': KafkaAdapter
        }

        if database_type not in adapters:
            raise ValueError(f"Unsupported database type: {database_type}")

        return adapters[database_type]

    @staticmethod
    def get_config_for_database(database_type: str, **kwargs) -> Dict[str, Any]:
        """
        Get configuration for specific database type

        Args:
            database_type: Type of database
            **kwargs: Additional configuration overrides

        Returns:
            Database configuration
        """
        config_methods = {
            'postgres': MigrationConfig.get_postgres_config,
            'redis': MigrationConfig.get_redis_config,
            'influxdb': MigrationConfig.get_influxdb_config,
            'elasticsearch': MigrationConfig.get_elasticsearch_config,
            'kafka': MigrationConfig.get_kafka_config
        }

        if database_type not in config_methods:
            raise ValueError(f"Unsupported database type: {database_type}")

        config = config_methods[database_type](**kwargs)
        config.update(kwargs)
        return config
