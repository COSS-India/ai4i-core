"""
Kafka Database Adapter
Handles Kafka-specific migration operations (topics, configs)
"""
from typing import Any, Dict, List, Optional
from kafka.admin import KafkaAdminClient, NewTopic, ConfigResource, ConfigResourceType
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
import json

from infrastructure.databases.core.base_adapter import BaseAdapter


class KafkaAdapter(BaseAdapter):
    """Kafka database adapter"""
    
    MIGRATIONS_TOPIC = "_migrations"
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Kafka adapter
        
        Args:
            config: Database configuration with keys:
                - bootstrap_servers: List of Kafka brokers
                - security_protocol: Security protocol (optional)
                - sasl_mechanism: SASL mechanism (optional)
                - sasl_username: SASL username (optional)
                - sasl_password: SASL password (optional)
        """
        super().__init__(config)
        self.admin_client = None
        self.producer = None
        
    def connect(self) -> None:
        """Establish Kafka connection"""
        bootstrap_servers = self.config.get('bootstrap_servers', ['localhost:9092'])
        
        # Build connection parameters
        conn_params = {
            'bootstrap_servers': bootstrap_servers,
        }
        
        # Add security if configured
        if self.config.get('security_protocol'):
            conn_params['security_protocol'] = self.config['security_protocol']
        if self.config.get('sasl_mechanism'):
            conn_params['sasl_mechanism'] = self.config['sasl_mechanism']
        if self.config.get('sasl_username'):
            conn_params['sasl_plain_username'] = self.config['sasl_username']
        if self.config.get('sasl_password'):
            conn_params['sasl_plain_password'] = self.config['sasl_password']
        
        self.admin_client = KafkaAdminClient(**conn_params)
        
        # Create producer for writing migration records
        self.producer = KafkaProducer(
            **conn_params,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        self.connection = self.admin_client
    
    def disconnect(self) -> None:
        """Close Kafka connection"""
        if self.producer:
            self.producer.close()
        if self.admin_client:
            self.admin_client.close()
    
    def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Execute Kafka command
        
        Args:
            query: Command (CREATE_TOPIC, DELETE_TOPIC, etc.)
            params: Command parameters
            
        Returns:
            Command result
        """
        command = query.strip().upper()
        
        if command == 'CREATE_TOPIC':
            return self._create_topic(params)
        elif command == 'DELETE_TOPIC':
            return self._delete_topic(params)
        elif command == 'ALTER_CONFIG':
            return self._alter_config(params)
        else:
            raise ValueError(f"Unsupported Kafka command: {command}")
    
    def create_migrations_table(self) -> None:
        """Create migrations tracking topic"""
        # Check if migrations topic exists
        existing_topics = self.admin_client.list_topics()
        
        if self.MIGRATIONS_TOPIC not in existing_topics:
            topic = NewTopic(
                name=self.MIGRATIONS_TOPIC,
                num_partitions=1,
                replication_factor=1,
                topic_configs={'retention.ms': str(365 * 24 * 60 * 60 * 1000)}  # 1 year
            )
            self.admin_client.create_topics([topic])
    
    def get_executed_migrations(self) -> List[str]:
        """Get list of executed migrations"""
        try:
            # Create consumer to read migrations topic
            consumer = KafkaConsumer(
                self.MIGRATIONS_TOPIC,
                bootstrap_servers=self.config.get('bootstrap_servers', ['localhost:9092']),
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                consumer_timeout_ms=1000,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            
            migrations = []
            migration_names = set()
            
            for message in consumer:
                data = message.value
                action = data.get('action')
                migration_name = data.get('migration')
                
                if action == 'record':
                    migration_names.add(migration_name)
                    migrations.append(migration_name)
                elif action == 'remove':
                    migration_names.discard(migration_name)
                    migrations = [m for m in migrations if m != migration_name]
            
            consumer.close()
            return migrations
        except Exception:
            return []
    
    def record_migration(self, migration_name: str, batch: int) -> None:
        """Record a migration as executed"""
        from datetime import datetime
        
        record = {
            'action': 'record',
            'migration': migration_name,
            'batch': batch,
            'executed_at': datetime.utcnow().isoformat()
        }
        
        self.producer.send(self.MIGRATIONS_TOPIC, value=record)
        self.producer.flush()
    
    def remove_migration(self, migration_name: str) -> None:
        """Remove a migration record"""
        from datetime import datetime
        
        record = {
            'action': 'remove',
            'migration': migration_name,
            'removed_at': datetime.utcnow().isoformat()
        }
        
        self.producer.send(self.MIGRATIONS_TOPIC, value=record)
        self.producer.flush()
    
    def get_last_batch_number(self) -> int:
        """Get the last batch number"""
        try:
            consumer = KafkaConsumer(
                self.MIGRATIONS_TOPIC,
                bootstrap_servers=self.config.get('bootstrap_servers', ['localhost:9092']),
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                consumer_timeout_ms=1000,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            
            max_batch = 0
            
            for message in consumer:
                data = message.value
                if data.get('action') == 'record':
                    batch = data.get('batch', 0)
                    if batch > max_batch:
                        max_batch = batch
            
            consumer.close()
            return max_batch
        except Exception:
            return 0
    
    def get_migrations_by_batch(self, batch: int) -> List[str]:
        """Get migrations from a specific batch"""
        try:
            consumer = KafkaConsumer(
                self.MIGRATIONS_TOPIC,
                bootstrap_servers=self.config.get('bootstrap_servers', ['localhost:9092']),
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                consumer_timeout_ms=1000,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            
            migrations = []
            
            for message in consumer:
                data = message.value
                if data.get('action') == 'record' and data.get('batch') == batch:
                    migrations.append(data.get('migration'))
            
            consumer.close()
            return migrations
        except Exception:
            return []
    
    # Kafka-specific helper methods
    
    def _create_topic(self, params: Dict[str, Any]) -> None:
        """Create a Kafka topic"""
        topic_name = params.get('name')
        num_partitions = params.get('partitions', 1)
        replication_factor = params.get('replication_factor', 1)
        topic_configs = params.get('configs', {})
        
        topic = NewTopic(
            name=topic_name,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
            topic_configs=topic_configs
        )
        
        self.admin_client.create_topics([topic])
    
    def _delete_topic(self, params: Dict[str, Any]) -> None:
        """Delete a Kafka topic"""
        topic_name = params.get('name')
        self.admin_client.delete_topics([topic_name])
    
    def _alter_config(self, params: Dict[str, Any]) -> None:
        """Alter topic configuration"""
        topic_name = params.get('name')
        configs = params.get('configs', {})
        
        resource = ConfigResource(ConfigResourceType.TOPIC, topic_name, configs)
        self.admin_client.alter_configs([resource])
    
    def create_topic(self, name: str, partitions: int = 1, 
                     replication_factor: int = 1, 
                     configs: Optional[Dict[str, str]] = None) -> None:
        """
        Create a new topic
        
        Args:
            name: Topic name
            partitions: Number of partitions
            replication_factor: Replication factor
            configs: Optional topic configurations
        """
        topic = NewTopic(
            name=name,
            num_partitions=partitions,
            replication_factor=replication_factor,
            topic_configs=configs or {}
        )
        self.admin_client.create_topics([topic])
    
    def delete_topic(self, name: str) -> None:
        """
        Delete a topic
        
        Args:
            name: Topic name
        """
        self.admin_client.delete_topics([name])
    
    def list_topics(self) -> List[str]:
        """
        List all topics
        
        Returns:
            List of topic names
        """
        return list(self.admin_client.list_topics())
    
    def alter_topic_config(self, topic_name: str, configs: Dict[str, str]) -> None:
        """
        Alter topic configuration
        
        Args:
            topic_name: Name of the topic
            configs: Configuration key-value pairs
        """
        resource = ConfigResource(ConfigResourceType.TOPIC, topic_name, configs)
        self.admin_client.alter_configs([resource])
