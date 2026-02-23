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
        base_url = (url or os.getenv("JAEGER_QUERY_URL", "http://jaeger:16686")).rstrip("/")
        # Jaeger may have a base path (e.g., /jaeger) configured via QUERY_BASE_PATH
        # Check environment variable or default to /jaeger if QUERY_BASE_PATH is set
        query_base_path = os.getenv("JAEGER_QUERY_BASE_PATH", "/jaeger")
        self.url = base_url
        self.base_path = query_base_path if query_base_path else ""
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        
        logger.info(f"JaegerQueryClient initialized for {self.url} with base_path={self.base_path}")
    
    async def close(self):
        """Close the HTTP client connection."""
        if self.client:
            await self.client.aclose()
    
    def _build_tags(self, organization_filter: Optional[str] = None, additional_tags: Optional[Dict[str, str]] = None) -> str:
        """
        Build Jaeger tags query string.
        
        Args:
            organization_filter: Tenant ID to filter by (None = admin)
                                Note: Despite the parameter name, this is actually tenant_id
            additional_tags: Additional tags to filter by
        
        Returns:
            Tags query string for Jaeger API
        """
        tags = []
        
        # Tenant ID filter (RBAC) - primary filter for multi-tenant RBAC
        if organization_filter:
            # Filter by tenant_id tag (primary)
            tags.append(f"tenant_id={organization_filter}")
            # Also include organization tag for backward compatibility
            tags.append(f"organization={organization_filter}")
        
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
            service: Service name to filter by (required by Jaeger API)
            operation: Operation name to filter by
            time_range: Dict with 'start_time' and 'end_time' (microseconds since epoch)
            tags: Additional tags to filter by
            limit: Maximum number of traces to return
        
        Returns:
            List of trace objects
        """
        try:
            # Jaeger API requires a service parameter
            # If no service is provided, we need to query all services and aggregate results
            if not service:
                # Get all services first
                all_services = await self.get_services_with_traces(organization_filter=organization_filter)
                if not all_services:
                    return []
                
                # Query each service and aggregate results
                all_traces = []
                for svc in all_services:
                    try:
                        traces = await self._search_traces_for_service(
                            organization_filter=organization_filter,
                            service=svc,
                            operation=operation,
                            time_range=time_range,
                            tags=tags,
                            limit=limit
                        )
                        all_traces.extend(traces)
                    except Exception as e:
                        logger.warning(f"Error querying traces for service {svc}: {e}")
                        continue
                
                # Sort by start time (newest first) and limit results
                all_traces.sort(key=lambda t: t.get("startTime", 0), reverse=True)
                return all_traces[:limit]
            
            # Single service query
            return await self._search_traces_for_service(
                organization_filter=organization_filter,
                service=service,
                operation=operation,
                time_range=time_range,
                tags=tags,
                limit=limit
            )
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error searching traces: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error searching traces: {e}", exc_info=True)
            raise
    
    async def _search_traces_for_service(
        self,
        organization_filter: Optional[str] = None,
        service: str = None,
        operation: Optional[str] = None,
        time_range: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Internal method to search traces for a specific service.
        """
        try:
            # Build query parameters
            params = {
                "limit": limit,
                "service": service  # Required by Jaeger
            }
            
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
            # Set Accept header to ensure JSON response (not HTML)
            headers = {"Accept": "application/json"}
            # Use base_path if configured (e.g., /jaeger/api/traces)
            api_path = f"{self.base_path}/api/traces" if self.base_path else "/api/traces"
            response = await self.client.get(
                f"{self.url}{api_path}",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            # Check if response has content
            if not response.content or len(response.content) == 0:
                logger.warning("Jaeger API returned empty response")
                return []
            
            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                logger.error(f"Jaeger API returned HTML instead of JSON. URL: {self.url}{api_path}")
                logger.error(f"Response (first 200 chars): {response.text[:200]}")
                return []
            
            # Try to parse JSON
            try:
                data = response.json()
            except Exception as e:
                logger.error(f"Failed to parse Jaeger response as JSON: {e}")
                logger.error(f"Content-Type: {content_type}")
                logger.error(f"Response content (first 500 chars): {response.text[:500]}")
                return []
            
            traces = data.get("data", [])
            
            # Filter traces by tenant_id if needed (client-side filtering as fallback)
            if organization_filter:
                filtered_traces = []
                for trace in traces:
                    tenant_found = False
                    spans = trace.get("spans", [])
                    for span in spans:
                        tags = span.get("tags", [])
                        for tag in tags:
                            # Check tenant_id tag first (primary filter)
                            if tag.get("key") == "tenant_id":
                                if tag.get("value") == organization_filter:
                                    tenant_found = True
                                    break
                            # Fallback: check organization tag for backward compatibility
                            elif tag.get("key") == "organization":
                                if tag.get("value") == organization_filter:
                                    tenant_found = True
                                    break
                        if tenant_found:
                            break
                    
                    if tenant_found:
                        filtered_traces.append(trace)
                
                return filtered_traces
            
            return traces
                
        except httpx.HTTPStatusError as e:
            # Handle 400 Bad Request (e.g., missing service parameter)
            if e.response.status_code == 400:
                error_body = e.response.text
                logger.warning(f"Jaeger API returned 400 Bad Request for service {service}: {error_body}")
                # Return empty list instead of raising error
                return []
            logger.error(f"HTTP error searching traces for service {service}: {e}", exc_info=True)
            raise
            
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
            # Set Accept header to ensure JSON response
            headers = {"Accept": "application/json"}
            # Use base_path if configured (e.g., /jaeger/api/traces/{trace_id})
            api_path = f"{self.base_path}/api/traces/{trace_id}" if self.base_path else f"/api/traces/{trace_id}"
            response = await self.client.get(
                f"{self.url}{api_path}",
                headers=headers
            )
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                logger.error(f"Jaeger API returned HTML instead of JSON. URL: {self.url}/api/traces/{trace_id}")
                return None
            
            # Try to parse JSON
            try:
                data = response.json()
            except Exception as e:
                logger.error(f"Failed to parse Jaeger trace response as JSON: {e}")
                logger.error(f"Content-Type: {content_type}")
                logger.error(f"Response (first 200 chars): {response.text[:200]}")
                return None
            
            traces = data.get("data", [])
            
            if not traces:
                return None
            
            trace = traces[0]  # Jaeger returns trace in array
            
            # RBAC check: Verify trace belongs to tenant_id
            if organization_filter:
                spans = trace.get("spans", [])
                tenant_found = False
                for span in spans:
                    tags = span.get("tags", [])
                    for tag in tags:
                        # Check tenant_id tag first (primary filter)
                        if tag.get("key") == "tenant_id":
                            if tag.get("value") == organization_filter:
                                tenant_found = True
                                break
                            # If tenant_id exists but doesn't match, continue checking other spans
                            # (don't return immediately - another span might have the correct tenant_id)
                        # Fallback: check organization tag for backward compatibility
                        elif tag.get("key") == "organization":
                            if tag.get("value") == organization_filter:
                                tenant_found = True
                                break
                    if tenant_found:
                        break
                
                if not tenant_found:
                    # No matching tenant_id or organization tag found in any span
                    logger.debug(f"Trace {trace_id} has no tenant_id or organization tag matching {organization_filter}, denying access")
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
            # Set Accept header to ensure JSON response
            headers = {"Accept": "application/json"}
            # Use base_path if configured (e.g., /jaeger/api/services)
            api_path = f"{self.base_path}/api/services" if self.base_path else "/api/services"
            response = await self.client.get(
                f"{self.url}{api_path}",
                headers=headers
            )
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                logger.error(f"Jaeger API returned HTML instead of JSON. URL: {self.url}/api/services")
                return []
            
            # Try to parse JSON
            try:
                data = response.json()
            except Exception as e:
                logger.error(f"Failed to parse Jaeger services response as JSON: {e}")
                logger.error(f"Content-Type: {content_type}")
                logger.error(f"Response (first 200 chars): {response.text[:200]}")
                return []
            
            services = data.get("data", [])
            
            # Note: Jaeger doesn't support organization filtering at service list level
            # We return all services, but actual trace queries will be filtered
            # This is acceptable as service names are not sensitive
            
            return services
            
        except httpx.HTTPStatusError as e:
            # Handle 400 Bad Request
            if e.response.status_code == 400:
                error_body = e.response.text
                logger.warning(f"Jaeger API returned 400 Bad Request for services: {error_body}")
                # Return empty list instead of raising error
                return []
            logger.error(f"HTTP error getting services: {e}", exc_info=True)
            raise
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
            # Set Accept header to ensure JSON response
            headers = {"Accept": "application/json"}
            params = {}
            # Use base_path if configured (e.g., /jaeger/api/services/{service}/operations)
            api_path = f"{self.base_path}/api/services/{service}/operations" if self.base_path else f"/api/services/{service}/operations"
            response = await self.client.get(
                f"{self.url}{api_path}",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                logger.error(f"Jaeger API returned HTML instead of JSON. URL: {self.url}/api/services/{service}/operations")
                return []
            
            # Try to parse JSON
            try:
                data = response.json()
            except Exception as e:
                logger.error(f"Failed to parse Jaeger operations response as JSON: {e}")
                logger.error(f"Content-Type: {content_type}")
                logger.error(f"Response (first 200 chars): {response.text[:200]}")
                return []
            
            operations = data.get("data", [])
            
            return operations
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting operations: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error getting operations: {e}", exc_info=True)
            raise

