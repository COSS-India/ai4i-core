"""
OpenSearch Query Client for AI4ICore Telemetry Library

Provides query capabilities for logs stored in OpenSearch with RBAC support.
Uses httpx directly to avoid monkey-patching and product check issues.
"""
import os
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)


class OpenSearchQueryClient:
    """
    Client for querying logs from OpenSearch with RBAC support.
    
    Supports tenant_id-based filtering for multi-tenant RBAC.
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
        self.verify_certs = verify_certs
        
        # Use httpx directly instead of elasticsearch client to avoid monkey-patching
        # This gives us full control over headers and avoids product check issues
        auth = None
        if self.username and self.password:
            auth = (self.username, self.password)
        
        self.client = httpx.AsyncClient(
            base_url=self.url,
            auth=auth,
            verify=verify_certs,
            timeout=30.0,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        logger.info(f"OpenSearchQueryClient initialized for {self.url} (using httpx)")
    
    async def _make_request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a request to OpenSearch API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/logs-*/_search")
            body: Request body as dict (will be JSON-encoded)
        
        Returns:
            Response JSON as dict
        """
        try:
            json_data = json.dumps(body) if body else None
            response = await self.client.request(
                method=method,
                url=path,
                content=json_data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenSearch API error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error connecting to OpenSearch: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenSearch response as JSON: {e}")
            raise
    
    async def close(self):
        """Close the OpenSearch client connection."""
        if self.client:
            await self.client.aclose()
    
    async def search_logs(
        self,
        organization_filter: Optional[str] = None,
        time_range: Optional[Dict[str, Any]] = None,
        service: Optional[str] = None,
        level: Optional[str] = None,
        search_text: Optional[str] = None,
        page: int = 1,
        size: int = 50,
        allowed_services: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Search logs with filters and pagination.
        
        Args:
            organization_filter: Tenant ID to filter by (None = admin, sees all)
                                Note: This parameter name is kept for backward compatibility,
                                but it now filters by tenant_id field
            time_range: Dict with 'start_time' and 'end_time' (ISO format or timestamp)
            service: Service name to filter by
            level: Log level to filter by (INFO, WARN, ERROR, DEBUG)
            search_text: Text to search in log messages
            page: Page number (1-indexed)
            size: Number of results per page
            allowed_services: Optional list of service names to filter by (for tenant subscriptions)
        
        Returns:
            Dict with 'logs' (list), 'total' (int), 'page' (int), 'size' (int)
        """
        try:
            # Build query
            must_clauses = []
            
            # Tenant ID filter (RBAC) - filters by tenant_id field
            if organization_filter:
                must_clauses.append({
                    "term": {"tenant_id": organization_filter}
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
            
            # Filter by allowed services (tenant subscriptions)
            # If allowed_services is provided, only show logs from those services
            if allowed_services is not None and len(allowed_services) > 0:
                must_clauses.append({
                    "terms": {"service": allowed_services}
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
            
            # Build request body
            request_body = {
                "query": query,
                "sort": [{"@timestamp": {"order": "desc"}}],
                "from": from_offset,
                "size": size,
                "_source": True
            }
            
            # Execute search using httpx directly
            path = f"/{self.index_pattern}/_search"
            response = await self._make_request("POST", path, request_body)
            
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
        time_range: Optional[Dict[str, Any]] = None,
        allowed_services: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get log aggregations and statistics.
        
        Args:
            organization_filter: Tenant ID to filter by (None = admin)
                                Note: This parameter name is kept for backward compatibility,
                                but it now filters by tenant_id field
            time_range: Dict with 'start_time' and 'end_time'
            allowed_services: Optional list of service names to filter by (for tenant subscriptions)
        
        Returns:
            Dict with statistics: total, by_level, by_service, error_count, warning_count
        """
        try:
            # Build base query (same as search_logs)
            must_clauses = []
            
            # Tenant ID filter (RBAC) - filters by tenant_id field
            if organization_filter:
                must_clauses.append({
                    "term": {"tenant_id": organization_filter}
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
            
            # Filter by allowed services (tenant subscriptions)
            if allowed_services is not None and len(allowed_services) > 0:
                must_clauses.append({
                    "terms": {"service": allowed_services}
                })
            
            query = {
                "bool": {
                    "must": must_clauses
                }
            } if must_clauses else {"match_all": {}}
            
            # Build aggregation request body
            request_body = {
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
            
            # Execute aggregation query using httpx directly
            path = f"/{self.index_pattern}/_search"
            response = await self._make_request("POST", path, request_body)
            
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
            organization_filter: Tenant ID to filter by (None = admin)
                                Note: This parameter name is kept for backward compatibility,
                                but it now filters by tenant_id field
            time_range: Dict with 'start_time' and 'end_time'
        
        Returns:
            List of service names
        """
        try:
            # Build base query
            must_clauses = []
            
            # Tenant ID filter (RBAC) - filters by tenant_id field
            if organization_filter:
                must_clauses.append({
                    "term": {"tenant_id": organization_filter}
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
            
            # Build aggregation request body
            request_body = {
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
            
            # Execute aggregation query using httpx directly
            path = f"/{self.index_pattern}/_search"
            response = await self._make_request("POST", path, request_body)
            
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

