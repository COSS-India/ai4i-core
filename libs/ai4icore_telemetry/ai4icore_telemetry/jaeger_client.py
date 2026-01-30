"""
Jaeger Query Client for AI4ICore Telemetry Library

Provides query capabilities for traces stored in Jaeger with RBAC support.
"""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class JaegerQueryClient:
    """
    Client for querying traces from Jaeger with RBAC support.
    
    Supports organization-based filtering for multi-tenant RBAC.
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize Jaeger Query API client.
        
        Args:
            url: Jaeger Query API URL (defaults to JAEGER_QUERY_URL env var)
            timeout: Request timeout in seconds
        """
        self.url = (url or os.getenv("JAEGER_QUERY_URL", "http://jaeger:16686")).rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        
        logger.info(f"JaegerQueryClient initialized for {self.url}")
    
    async def close(self):
        """Close the HTTP client connection."""
        if self.client:
            await self.client.aclose()
    
    def _build_tags(self, organization_filter: Optional[str] = None, additional_tags: Optional[Dict[str, str]] = None) -> str:
        """
        Build Jaeger tags query string.
        
        Args:
            organization_filter: Organization ID to filter by (None = admin)
            additional_tags: Additional tags to filter by
        
        Returns:
            Tags query string for Jaeger API
        """
        tags = []
        
        # Organization filter (RBAC)
        if organization_filter:
            # Try organization attribute first
            tags.append(f"organization={organization_filter}")
            # Fallback: also try user.id if available (for backward compatibility)
            # Note: This is a fallback, primary filter is organization
        
        # Additional tags
        if additional_tags:
            for key, value in additional_tags.items():
                tags.append(f"{key}={value}")
        
        return "&".join(tags) if tags else ""
    
    async def search_traces(
        self,
        organization_filter: Optional[str] = None,
        service: Optional[str] = None,
        operation: Optional[str] = None,
        time_range: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search traces with filters.
        
        Args:
            organization_filter: Organization ID to filter by (None = admin, sees all)
            service: Service name to filter by
            operation: Operation name to filter by
            time_range: Dict with 'start_time' and 'end_time' (microseconds since epoch)
            tags: Additional tags to filter by
            limit: Maximum number of traces to return
        
        Returns:
            List of trace objects
        """
        try:
            # Build query parameters
            params = {
                "limit": limit
            }
            
            # Service filter
            if service:
                params["service"] = service
            
            # Operation filter
            if operation:
                params["operation"] = operation
            
            # Time range
            if time_range:
                start_time = time_range.get("start_time")
                end_time = time_range.get("end_time")
                
                if start_time:
                    params["start"] = start_time
                if end_time:
                    params["end"] = end_time
            else:
                # Default: last hour
                now = int(datetime.now().timestamp() * 1000000)  # microseconds
                hour_ago = now - (3600 * 1000000)
                params["start"] = hour_ago
                params["end"] = now
            
            # Tags (including organization filter)
            # Build tags string for Jaeger API
            tag_string = self._build_tags(organization_filter, tags)
            if tag_string:
                params["tags"] = tag_string
            
            # Call Jaeger Query API
            response = await self.client.get(
                f"{self.url}/api/traces",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            traces = data.get("data", [])
            
            # Filter traces by organization if needed (client-side filtering as fallback)
            if organization_filter:
                filtered_traces = []
                for trace in traces:
                    # Check if any span has the organization attribute
                    spans = trace.get("spans", [])
                    for span in spans:
                        tags = span.get("tags", [])
                        span_org = None
                        for tag in tags:
                            if tag.get("key") == "organization":
                                span_org = tag.get("value")
                                break
                        
                        # If span has organization and it matches, include trace
                        if span_org == organization_filter:
                            filtered_traces.append(trace)
                            break
                
                return filtered_traces
            
            return traces
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error searching traces: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error searching traces: {e}", exc_info=True)
            raise
    
    async def get_trace_by_id(
        self,
        trace_id: str,
        organization_filter: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific trace by ID.
        
        Args:
            trace_id: Trace ID (hex string)
            organization_filter: Organization ID to filter by (None = admin)
        
        Returns:
            Trace object or None if not found or not accessible
        """
        try:
            # Call Jaeger Query API
            response = await self.client.get(
                f"{self.url}/api/traces/{trace_id}"
            )
            response.raise_for_status()
            
            data = response.json()
            traces = data.get("data", [])
            
            if not traces:
                return None
            
            trace = traces[0]  # Jaeger returns trace in array
            
            # RBAC check: Verify trace belongs to organization
            if organization_filter:
                spans = trace.get("spans", [])
                for span in spans:
                    tags = span.get("tags", [])
                    for tag in tags:
                        if tag.get("key") == "organization":
                            if tag.get("value") == organization_filter:
                                return trace
                            else:
                                # Organization doesn't match
                                return None
                
                # No organization found in trace - check user.id as fallback
                # This is for backward compatibility with old traces
                for span in spans:
                    tags = span.get("tags", [])
                    for tag in tags:
                        if tag.get("key") == "user.id":
                            # If user.id exists, we'd need to check if user belongs to org
                            # For now, if no organization tag, deny access
                            return None
                
                # No organization or user.id found - deny access
                return None
            
            return trace
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Trace {trace_id} not found")
                return None
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting trace: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error getting trace: {e}", exc_info=True)
            raise
    
    async def get_services_with_traces(
        self,
        organization_filter: Optional[str] = None
    ) -> List[str]:
        """
        Get list of services that have traces.
        
        Args:
            organization_filter: Organization ID to filter by (None = admin)
        
        Returns:
            List of service names
        """
        try:
            # Call Jaeger Query API
            response = await self.client.get(
                f"{self.url}/api/services"
            )
            response.raise_for_status()
            
            data = response.json()
            services = data.get("data", [])
            
            # Note: Jaeger doesn't support organization filtering at service list level
            # We return all services, but actual trace queries will be filtered
            # This is acceptable as service names are not sensitive
            
            return services
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting services: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error getting services: {e}", exc_info=True)
            raise
    
    async def get_operations_for_service(
        self,
        service: str,
        organization_filter: Optional[str] = None
    ) -> List[str]:
        """
        Get list of operations for a specific service.
        
        Args:
            service: Service name
            organization_filter: Organization ID to filter by (None = admin)
        
        Returns:
            List of operation names
        """
        try:
            # Call Jaeger Query API
            params = {}
            response = await self.client.get(
                f"{self.url}/api/services/{service}/operations",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            operations = data.get("data", [])
            
            return operations
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting operations: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error getting operations: {e}", exc_info=True)
            raise

