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
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'user': os.getenv('POSTGRES_USER', 'dhruva_user'),
            'password': os.getenv('POSTGRES_PASSWORD', 'dhruva_password'),
            'database': database,
            'async': False  # Set to True for async operations
        }
    
    @staticmethod
    def get_redis_config() -> Dict[str, Any]:
        """Get Redis configuration"""
        return {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'password': os.getenv('REDIS_PASSWORD', None),
            'db': int(os.getenv('REDIS_DB', 0))
        }
    
    @staticmethod
    def get_influxdb_config() -> Dict[str, Any]:
        """Get InfluxDB configuration"""
        return {
            'url': os.getenv('INFLUXDB_URL', 'http://localhost:8086'),
            'token': os.getenv('INFLUXDB_TOKEN', ''),
            'org': os.getenv('INFLUXDB_ORG', 'ai4i'),
            'bucket': os.getenv('INFLUXDB_BUCKET', 'ai_metrics')
        }
    
    @staticmethod
    def get_elasticsearch_config() -> Dict[str, Any]:
        """Get Elasticsearch configuration"""
        hosts = os.getenv('ELASTICSEARCH_HOSTS', 'http://localhost:9200')
        return {
            'hosts': hosts.split(','),
            'username': os.getenv('ELASTICSEARCH_USERNAME', None),
            'password': os.getenv('ELASTICSEARCH_PASSWORD', None),
            'api_key': os.getenv('ELASTICSEARCH_API_KEY', None),
            'verify_certs': os.getenv('ELASTICSEARCH_VERIFY_CERTS', 'true').lower() == 'true'
        }
    
    @staticmethod
    def get_kafka_config() -> Dict[str, Any]:
        """Get Kafka configuration"""
        bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        return {
            'bootstrap_servers': bootstrap_servers.split(','),
            'security_protocol': os.getenv('KAFKA_SECURITY_PROTOCOL', None),
            'sasl_mechanism': os.getenv('KAFKA_SASL_MECHANISM', None),
            'sasl_username': os.getenv('KAFKA_SASL_USERNAME', None),
            'sasl_password': os.getenv('KAFKA_SASL_PASSWORD', None)
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
        from infrastructure.migrations.adapters import (
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
