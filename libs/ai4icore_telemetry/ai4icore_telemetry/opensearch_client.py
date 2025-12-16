"""
OpenSearch Client for Log Storage

This module provides OpenSearch client setup and utilities for storing logs.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from elasticsearch import AsyncElasticsearch
    OPENSEARCH_AVAILABLE = True
except ImportError:
    OPENSEARCH_AVAILABLE = False
    logger.warning("Elasticsearch client not available (used for OpenSearch)")


def get_opensearch_client() -> Optional[AsyncElasticsearch]:
    """
    Create and return OpenSearch client.
    
    Returns:
        AsyncElasticsearch client instance or None if unavailable
    """
    if not OPENSEARCH_AVAILABLE:
        logger.warning("OpenSearch client not available")
        return None
    
    try:
        opensearch_url = os.getenv("OPENSEARCH_URL", "http://opensearch:9200")
        opensearch_username = os.getenv("OPENSEARCH_USERNAME", None)
        opensearch_password = os.getenv("OPENSEARCH_PASSWORD", None)
        
        # Only use auth if credentials are provided (security may be disabled)
        auth = (opensearch_username, opensearch_password) if opensearch_username and opensearch_password else None
        
        client = AsyncElasticsearch(
            [opensearch_url],
            basic_auth=auth,
            verify_certs=False,  # For local development
            request_timeout=30,
        )
        
        logger.info(f"✅ OpenSearch client initialized: {opensearch_url}")
        return client
    
    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenSearch client: {e}")
        return None


async def create_log_index(client: AsyncElasticsearch, index_name: str = "logs") -> bool:
    """
    Create log index in OpenSearch if it doesn't exist.
    
    Args:
        client: OpenSearch client
        index_name: Name of the index to create
    
    Returns:
        True if successful, False otherwise
    """
    if not client:
        return False
    
    try:
        # Check if index exists
        exists = await client.indices.exists(index=index_name)
        
        if not exists:
            # Create index with mapping
            await client.indices.create(
                index=index_name,
                body={
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                    },
                    "mappings": {
                        "properties": {
                            "@timestamp": {"type": "date"},
                            "level": {"type": "keyword"},
                            "service": {"type": "keyword"},
                            "message": {"type": "text"},
                            "trace_id": {"type": "keyword"},
                            "span_id": {"type": "keyword"},
                            "correlation_id": {"type": "keyword"},
                            "context": {"type": "object"},
                        }
                    }
                }
            )
            logger.info(f"✅ Created log index: {index_name}")
        else:
            logger.info(f"ℹ️ Log index already exists: {index_name}")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Failed to create log index: {e}")
        return False
