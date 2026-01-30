"""
OpenSearch Query Client for AI4ICore Telemetry Library

Provides query capabilities for logs stored in OpenSearch with RBAC support.
"""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from elasticsearch import AsyncElasticsearch

logger = logging.getLogger(__name__)


class OpenSearchQueryClient:
    """
    Client for querying logs from OpenSearch with RBAC support.
    
    Supports organization-based filtering for multi-tenant RBAC.
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_certs: bool = False,
        index_pattern: str = "logs-*"
    ):
        """
        Initialize OpenSearch client.
        
        Args:
            url: OpenSearch URL (defaults to OPENSEARCH_URL env var)
            username: OpenSearch username (defaults to OPENSEARCH_USERNAME env var)
            password: OpenSearch password (defaults to OPENSEARCH_PASSWORD env var)
            verify_certs: Whether to verify SSL certificates
            index_pattern: Index pattern to search (default: "logs-*")
        """
        self.url = url or os.getenv("OPENSEARCH_URL", "http://opensearch:9200")
        self.username = username or os.getenv("OPENSEARCH_USERNAME", "admin")
        self.password = password or os.getenv("OPENSEARCH_PASSWORD", "admin")
        self.index_pattern = index_pattern
        
        # Initialize Elasticsearch client (compatible with OpenSearch)
        # Using elasticsearch 8.x which is fully compatible with OpenSearch
        # Note: We use the 'elasticsearch' Python library to connect to OpenSearch
        # because OpenSearch is API-compatible with Elasticsearch
        # 
        # IMPORTANT: 
        # 1. OpenSearch doesn't support the default 'application/vnd.elasticsearch+json' 
        #    Content-Type header that elasticsearch 8.x sends
        # 2. The client has a product check that rejects non-Elasticsearch servers
        #    We need to monkey-patch to bypass this check and force the correct Content-Type
        self.client = AsyncElasticsearch(
            [self.url],
            basic_auth=(self.username, self.password) if self.username and self.password else None,
            verify_certs=verify_certs,
            meta_header=False  # Disable meta header (doesn't disable product check, but helps)
        )
        
        # Monkey-patch to bypass product check and fix Content-Type
        # The product check happens in _perform_request, not in transport
        # We need to patch both the client's _perform_request and the transport
        
        # 1. Patch the client's _perform_request to catch and bypass UnsupportedProductError
        original_client_perform_request = self.client._perform_request
        
        async def patched_client_perform_request(*args, **kwargs):
            try:
                return await original_client_perform_request(*args, **kwargs)
            except Exception as e:
                error_str = str(e)
                error_type = type(e).__name__
                # Catch UnsupportedProductError - the request actually succeeded, but product check failed
                if 'UnsupportedProductError' in error_type or 'not Elasticsearch' in error_str or 'unknown product' in error_str:
                    logger.warning(f"Product check error bypassed (OpenSearch is API-compatible): {error_str}")
                    # The UnsupportedProductError exception contains the actual response in meta and body
                    # Extract them and return a proper ApiResponse object
                    if hasattr(e, 'meta') and hasattr(e, 'body'):
                        from elastic_transport import ApiResponse
                        # Return the response with the actual data (the request succeeded, only the product check failed)
                        return ApiResponse(meta=e.meta, body=e.body)
                    # Fallback: if meta/body not available, log error
                    logger.error(f"Could not extract response from product check error: {e}")
                    raise RuntimeError(f"OpenSearch product check bypassed, but could not extract response: {error_str}") from None
                raise
        
        # 2. Patch the transport to force correct Content-Type
        original_transport_perform_request = self.client.transport.perform_request
        
        async def patched_transport_perform_request(method, url, headers=None, **kwargs):
            if headers is None:
                headers = {}
            # Force Content-Type to application/json for OpenSearch compatibility
            headers['Content-Type'] = 'application/json'
            # Remove any elasticsearch-specific content type variants
            for key in list(headers.keys()):
                if 'elasticsearch' in str(key).lower() or 'vnd.elasticsearch' in str(key).lower():
                    del headers[key]
            return await original_transport_perform_request(method, url, headers=headers, **kwargs)
        
        # Apply both patches
        self.client._perform_request = patched_client_perform_request
        self.client.transport.perform_request = patched_transport_perform_request
        
        # 3. Most importantly: Disable the product check by monkey-patching the check itself
        # The check happens in _async/client/_base.py in _verify_elasticsearch
        try:
            from elasticsearch._async.client import _base
            original_verify = _base.AsyncElasticsearch._verify_elasticsearch
            
            async def patched_verify(self, response):
                # Skip the product verification - just return
                logger.debug("Skipping Elasticsearch product verification for OpenSearch compatibility")
                return
            
            _base.AsyncElasticsearch._verify_elasticsearch = patched_verify
            logger.info("Product check disabled via monkey-patch")
        except (ImportError, AttributeError) as e:
            logger.warning(f"Could not disable product check via monkey-patch: {e}")
        
        logger.info(f"OpenSearchQueryClient initialized for {self.url}")
    
    async def close(self):
        """Close the OpenSearch client connection."""
        if self.client:
            await self.client.close()
    
    async def search_logs(
        self,
        organization_filter: Optional[str] = None,
        time_range: Optional[Dict[str, Any]] = None,
        service: Optional[str] = None,
        level: Optional[str] = None,
        search_text: Optional[str] = None,
        page: int = 1,
        size: int = 50
    ) -> Dict[str, Any]:
        """
        Search logs with filters and pagination.
        
        Args:
            organization_filter: Organization ID to filter by (None = admin, sees all)
            time_range: Dict with 'start_time' and 'end_time' (ISO format or timestamp)
            service: Service name to filter by
            level: Log level to filter by (INFO, WARN, ERROR, DEBUG)
            search_text: Text to search in log messages
            page: Page number (1-indexed)
            size: Number of results per page
        
        Returns:
            Dict with 'logs' (list), 'total' (int), 'page' (int), 'size' (int)
        """
        try:
            # Build query
            must_clauses = []
            
            # Organization filter (RBAC)
            if organization_filter:
                must_clauses.append({
                    "term": {"organization": organization_filter}
                })
            
            # Time range filter
            if time_range:
                start_time = time_range.get("start_time")
                end_time = time_range.get("end_time")
                
                if start_time or end_time:
                    time_filter = {}
                    if start_time:
                        time_filter["gte"] = start_time
                    if end_time:
                        time_filter["lte"] = end_time
                    
                    must_clauses.append({
                        "range": {
                            "@timestamp": time_filter
                        }
                    })
            
            # Service filter
            if service:
                must_clauses.append({
                    "term": {"service": service}
                })
            
            # Level filter
            if level:
                must_clauses.append({
                    "term": {"level": level.upper()}
                })
            
            # Text search
            if search_text:
                must_clauses.append({
                    "multi_match": {
                        "query": search_text,
                        "fields": ["message", "message.keyword"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                })
            
            # Build final query
            query = {
                "bool": {
                    "must": must_clauses
                }
            } if must_clauses else {"match_all": {}}
            
            # Calculate from/size for pagination
            from_offset = (page - 1) * size
            
            # Execute search
            response = await self.client.search(
                index=self.index_pattern,
                body={
                    "query": query,
                    "sort": [{"@timestamp": {"order": "desc"}}],
                    "from": from_offset,
                    "size": size,
                    "_source": True
                }
            )
            
            # Extract results
            hits = response.get("hits", {})
            total = hits.get("total", {}).get("value", 0)
            logs = [hit["_source"] for hit in hits.get("hits", [])]
            
            return {
                "logs": logs,
                "total": total,
                "page": page,
                "size": size,
                "total_pages": (total + size - 1) // size if total > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error searching logs: {e}", exc_info=True)
            raise
    
    async def get_log_aggregations(
        self,
        organization_filter: Optional[str] = None,
        time_range: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get log aggregations and statistics.
        
        Args:
            organization_filter: Organization ID to filter by (None = admin)
            time_range: Dict with 'start_time' and 'end_time'
        
        Returns:
            Dict with statistics: total, by_level, by_service, error_count, warning_count
        """
        try:
            # Build base query (same as search_logs)
            must_clauses = []
            
            if organization_filter:
                must_clauses.append({
                    "term": {"organization": organization_filter}
                })
            
            if time_range:
                start_time = time_range.get("start_time")
                end_time = time_range.get("end_time")
                
                if start_time or end_time:
                    time_filter = {}
                    if start_time:
                        time_filter["gte"] = start_time
                    if end_time:
                        time_filter["lte"] = end_time
                    
                    must_clauses.append({
                        "range": {
                            "@timestamp": time_filter
                        }
                    })
            
            query = {
                "bool": {
                    "must": must_clauses
                }
            } if must_clauses else {"match_all": {}}
            
            # Execute aggregation query
            response = await self.client.search(
                index=self.index_pattern,
                body={
                    "query": query,
                    "size": 0,  # Don't return documents, only aggregations
                    "aggs": {
                        "by_level": {
                            "terms": {
                                "field": "level",
                                "size": 10
                            }
                        },
                        "by_service": {
                            "terms": {
                                "field": "service",
                                "size": 20
                            }
                        },
                        "error_count": {
                            "filter": {
                                "term": {"level": "ERROR"}
                            }
                        },
                        "warning_count": {
                            "filter": {
                                "term": {"level": "WARN"}
                            }
                        }
                    }
                }
            )
            
            # Extract aggregations
            aggs = response.get("aggregations", {})
            total = response.get("hits", {}).get("total", {}).get("value", 0)
            
            by_level = {
                bucket["key"]: bucket["doc_count"]
                for bucket in aggs.get("by_level", {}).get("buckets", [])
            }
            
            by_service = {
                bucket["key"]: bucket["doc_count"]
                for bucket in aggs.get("by_service", {}).get("buckets", [])
            }
            
            error_count = aggs.get("error_count", {}).get("doc_count", 0)
            warning_count = aggs.get("warning_count", {}).get("doc_count", 0)
            
            return {
                "total": total,
                "by_level": by_level,
                "by_service": by_service,
                "error_count": error_count,
                "warning_count": warning_count
            }
            
        except Exception as e:
            logger.error(f"Error getting log aggregations: {e}", exc_info=True)
            raise
    
    async def get_services_with_logs(
        self,
        organization_filter: Optional[str] = None,
        time_range: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Get list of services that have logs.
        
        Args:
            organization_filter: Organization ID to filter by (None = admin)
            time_range: Dict with 'start_time' and 'end_time'
        
        Returns:
            List of service names
        """
        try:
            # Build base query
            must_clauses = []
            
            if organization_filter:
                must_clauses.append({
                    "term": {"organization": organization_filter}
                })
            
            if time_range:
                start_time = time_range.get("start_time")
                end_time = time_range.get("end_time")
                
                if start_time or end_time:
                    time_filter = {}
                    if start_time:
                        time_filter["gte"] = start_time
                    if end_time:
                        time_filter["lte"] = end_time
                    
                    must_clauses.append({
                        "range": {
                            "@timestamp": time_filter
                        }
                    })
            
            query = {
                "bool": {
                    "must": must_clauses
                }
            } if must_clauses else {"match_all": {}}
            
            # Execute aggregation query
            response = await self.client.search(
                index=self.index_pattern,
                body={
                    "query": query,
                    "size": 0,
                    "aggs": {
                        "services": {
                            "terms": {
                                "field": "service",
                                "size": 100  # Get up to 100 services
                            }
                        }
                    }
                }
            )
            
            # Extract service names
            aggs = response.get("aggregations", {})
            services = [
                bucket["key"]
                for bucket in aggs.get("services", {}).get("buckets", [])
            ]
            
            return services
            
        except Exception as e:
            logger.error(f"Error getting services with logs: {e}", exc_info=True)
            raise

