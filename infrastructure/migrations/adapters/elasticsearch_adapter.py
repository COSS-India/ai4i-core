"""
Elasticsearch Database Adapter
Handles Elasticsearch-specific migration operations
"""
from typing import Any, Dict, List, Optional
from elasticsearch import Elasticsearch
from datetime import datetime

from infrastructure.migrations.core.base_adapter import BaseAdapter


class ElasticsearchAdapter(BaseAdapter):
    """Elasticsearch database adapter"""
    
    MIGRATIONS_INDEX = "_migrations"
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Elasticsearch adapter
        
        Args:
            config: Database configuration with keys:
                - hosts: List of Elasticsearch hosts
                - username: Username (optional)
                - password: Password (optional)
                - api_key: API key (optional)
        """
        super().__init__(config)
        self.client = None
        
    def connect(self) -> None:
        """Establish Elasticsearch connection"""
        hosts = self.config.get('hosts', ['http://localhost:9200'])
        
        # Build connection parameters
        conn_params = {'hosts': hosts}
        
        if self.config.get('username') and self.config.get('password'):
            conn_params['basic_auth'] = (
                self.config['username'], 
                self.config['password']
            )
        elif self.config.get('api_key'):
            conn_params['api_key'] = self.config['api_key']
        
        # SSL verification
        if self.config.get('verify_certs') is False:
            conn_params['verify_certs'] = False
        
        self.client = Elasticsearch(**conn_params)
        self.connection = self.client
        
        # Verify connection
        if not self.client.ping():
            raise ConnectionError("Failed to connect to Elasticsearch")
    
    def disconnect(self) -> None:
        """Close Elasticsearch connection"""
        if self.client:
            self.client.close()
    
    def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Execute Elasticsearch query
        
        Args:
            query: Query DSL (as JSON string) or command
            params: Optional parameters
            
        Returns:
            Query result
        """
        import json
        
        # Parse query as JSON
        try:
            query_body = json.loads(query)
            index = params.get('index', '_all') if params else '_all'
            return self.client.search(index=index, body=query_body)
        except json.JSONDecodeError:
            raise ValueError("Query must be valid JSON (Elasticsearch Query DSL)")
    
    def create_migrations_table(self) -> None:
        """Create migrations tracking index"""
        if not self.client.indices.exists(index=self.MIGRATIONS_INDEX):
            self.client.indices.create(
                index=self.MIGRATIONS_INDEX,
                body={
                    "mappings": {
                        "properties": {
                            "migration": {"type": "keyword"},
                            "batch": {"type": "integer"},
                            "executed_at": {"type": "date"}
                        }
                    }
                }
            )
    
    def get_executed_migrations(self) -> List[str]:
        """Get list of executed migrations"""
        try:
            if not self.client.indices.exists(index=self.MIGRATIONS_INDEX):
                return []
            
            result = self.client.search(
                index=self.MIGRATIONS_INDEX,
                body={
                    "query": {"match_all": {}},
                    "sort": [{"executed_at": {"order": "asc"}}],
                    "size": 1000
                }
            )
            
            migrations = []
            for hit in result['hits']['hits']:
                migrations.append(hit['_source']['migration'])
            
            return migrations
        except Exception:
            return []
    
    def record_migration(self, migration_name: str, batch: int) -> None:
        """Record a migration as executed"""
        doc = {
            "migration": migration_name,
            "batch": batch,
            "executed_at": datetime.utcnow().isoformat()
        }
        
        self.client.index(
            index=self.MIGRATIONS_INDEX,
            id=migration_name,  # Use migration name as document ID
            document=doc
        )
    
    def remove_migration(self, migration_name: str) -> None:
        """Remove a migration record"""
        try:
            self.client.delete(
                index=self.MIGRATIONS_INDEX,
                id=migration_name
            )
        except Exception:
            pass
    
    def get_last_batch_number(self) -> int:
        """Get the last batch number"""
        try:
            if not self.client.indices.exists(index=self.MIGRATIONS_INDEX):
                return 0
            
            result = self.client.search(
                index=self.MIGRATIONS_INDEX,
                body={
                    "size": 0,
                    "aggs": {
                        "max_batch": {
                            "max": {"field": "batch"}
                        }
                    }
                }
            )
            
            max_batch = result['aggregations']['max_batch']['value']
            return int(max_batch) if max_batch else 0
        except Exception:
            return 0
    
    def get_migrations_by_batch(self, batch: int) -> List[str]:
        """Get migrations from a specific batch"""
        result = self.client.search(
            index=self.MIGRATIONS_INDEX,
            body={
                "query": {
                    "term": {"batch": batch}
                },
                "sort": [{"executed_at": {"order": "asc"}}],
                "size": 1000
            }
        )
        
        migrations = []
        for hit in result['hits']['hits']:
            migrations.append(hit['_source']['migration'])
        
        return migrations
    
    # Elasticsearch-specific helper methods
    
    def create_index(self, index_name: str, mappings: Dict[str, Any], 
                     settings: Optional[Dict[str, Any]] = None) -> None:
        """
        Create an index
        
        Args:
            index_name: Name of the index
            mappings: Index mappings
            settings: Optional index settings
        """
        body = {"mappings": mappings}
        if settings:
            body["settings"] = settings
        
        self.client.indices.create(index=index_name, body=body)
    
    def delete_index(self, index_name: str) -> None:
        """
        Delete an index
        
        Args:
            index_name: Name of the index
        """
        if self.client.indices.exists(index=index_name):
            self.client.indices.delete(index=index_name)
    
    def put_mapping(self, index_name: str, mappings: Dict[str, Any]) -> None:
        """
        Update index mappings
        
        Args:
            index_name: Name of the index
            mappings: New mappings
        """
        self.client.indices.put_mapping(index=index_name, body=mappings)
    
    def create_index_template(self, template_name: str, template_body: Dict[str, Any]) -> None:
        """
        Create an index template
        
        Args:
            template_name: Name of the template
            template_body: Template definition
        """
        self.client.indices.put_index_template(
            name=template_name,
            body=template_body
        )
    
    def delete_index_template(self, template_name: str) -> None:
        """
        Delete an index template
        
        Args:
            template_name: Name of the template
        """
        self.client.indices.delete_index_template(name=template_name)
