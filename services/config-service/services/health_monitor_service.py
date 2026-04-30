"""
Health Monitoring Service

Provides automatic periodic health checks with retry logic, exponential backoff,
and multi-endpoint aggregation.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass

from models.service_registry_models import ServiceInstance, ServiceStatus
from repositories.service_registry_repository import ServiceRegistryRepository
from redis.asyncio import Redis


logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    service_name: str
    instance_id: Optional[str]
    endpoint_url: str
    is_healthy: bool
    response_time_ms: float
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


@dataclass
class AggregatedHealthResult:
    """Aggregated health check result for a service"""
    service_name: str
    overall_status: ServiceStatus
    total_instances: int
    healthy_instances: int
    unhealthy_instances: int
    check_results: List[HealthCheckResult]
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class HealthMonitorService:
    """Service for monitoring health of registered services"""

    def __init__(
        self,
        repository: ServiceRegistryRepository,
        redis_client: Redis,
        default_timeout: float = 3.0,
        max_retries: int = 3,
        initial_retry_delay: float = 1.0,
        max_retry_delay: float = 30.0,
        retry_backoff_multiplier: float = 2.0,
    ):
        self.repository = repository
        self.redis = redis_client
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.max_retry_delay = max_retry_delay
        self.retry_backoff_multiplier = retry_backoff_multiplier
        self._session: Optional[Any] = None  # aiohttp.ClientSession (lazy import)

    async def _get_session(self):
        """Get or create aiohttp session"""
        try:
            import aiohttp
        except ImportError:
            raise ImportError(
                "aiohttp is required for health monitoring. "
                "Install it with: pip install aiohttp>=3.9.0"
            )
        
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.default_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def check_endpoint_health(
        self,
        url: str,
        timeout: Optional[float] = None,
        retry: bool = True,
    ) -> HealthCheckResult:
        """
        Check health of a single endpoint with retry logic and exponential backoff.

        Args:
            url: Health check endpoint URL
            timeout: Request timeout in seconds
            retry: Whether to retry on failure

        Returns:
            HealthCheckResult with health status and metrics
        """
        try:
            import aiohttp
        except ImportError:
            raise ImportError(
                "aiohttp is required for health monitoring. "
                "Install it with: pip install aiohttp>=3.9.0"
            )
        
        timeout = timeout or self.default_timeout
        check_timeout = aiohttp.ClientTimeout(total=timeout)
        last_error = None
        last_status_code = None

        for attempt in range(self.max_retries if retry else 1):
            try:
                start_time = time.time()
                session = await self._get_session()
                
                async with session.get(url, timeout=check_timeout) as resp:
                    response_time = (time.time() - start_time) * 1000  # Convert to ms
                    status_code = resp.status
                    last_status_code = status_code
                    
                    # Consider 2xx and 3xx as healthy
                    is_healthy = 200 <= status_code < 400
                    
                    if is_healthy:
                        return HealthCheckResult(
                            service_name="",  # Will be set by caller
                            instance_id=None,
                            endpoint_url=url,
                            is_healthy=True,
                            response_time_ms=response_time,
                            status_code=status_code,
                        )
                    else:
                        last_error = f"HTTP {status_code}"
                        
            except asyncio.TimeoutError:
                last_error = "Timeout"
                response_time = timeout * 1000
            except aiohttp.ClientError as e:
                last_error = f"Client error: {str(e)}"
                response_time = 0
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                response_time = 0

            # If retry is enabled and not the last attempt, wait with exponential backoff
            if retry and attempt < self.max_retries - 1:
                delay = min(
                    self.initial_retry_delay * (self.retry_backoff_multiplier ** attempt),
                    self.max_retry_delay
                )
                logger.debug(
                    f"Health check failed for {url} (attempt {attempt + 1}/{self.max_retries}), "
                    f"retrying in {delay:.2f}s"
                )
                await asyncio.sleep(delay)

        # All retries exhausted or retry disabled
        return HealthCheckResult(
            service_name="",
            instance_id=None,
            endpoint_url=url,
            is_healthy=False,
            response_time_ms=response_time if 'response_time' in locals() else 0,
            status_code=last_status_code,
            error_message=last_error,
        )

    async def check_service_health(
        self,
        service_name: str,
        instances: List[ServiceInstance],
        additional_endpoints: Optional[List[str]] = None,
    ) -> AggregatedHealthResult:
        """
        Check health of all instances and endpoints for a service.

        Args:
            service_name: Name of the service
            instances: List of service instances to check
            additional_endpoints: Additional endpoints to check (e.g., /ready, /live)

        Returns:
            AggregatedHealthResult with overall health status
        """
        check_results: List[HealthCheckResult] = []
        additional_endpoints = additional_endpoints or []
        instance_health_status: Dict[str, bool] = {}  # Track instance health

        # Check all instances
        for instance in instances:
            endpoints_to_check = []
            instance_is_healthy = False
            
            # Primary health check URL
            if instance.health_check_url:
                endpoints_to_check.append(instance.health_check_url)
            elif instance.service_url:
                # Try common health check paths
                for path in ["/health", "/api/v1/health", f"/api/v1/{service_name.split('-')[0]}/health"]:
                    endpoints_to_check.append(f"{instance.service_url.rstrip('/')}{path}")
            
            # Add additional endpoints
            if instance.service_url:
                for endpoint in additional_endpoints:
                    endpoints_to_check.append(f"{instance.service_url.rstrip('/')}{endpoint}")

            # Check each endpoint for this instance
            for endpoint_url in endpoints_to_check:
                result = await self.check_endpoint_health(endpoint_url)
                result.service_name = service_name
                result.instance_id = instance.instance_id
                check_results.append(result)
                
                # If at least one endpoint is healthy, consider instance healthy
                if result.is_healthy:
                    instance_is_healthy = True
                    # Don't break - continue checking other endpoints for comprehensive data
                    # But mark instance as healthy
                    break
            
            # Track instance health status
            instance_key = instance.instance_id or f"{instance.service_url}"
            instance_health_status[instance_key] = instance_is_healthy

        # Aggregate results - count healthy instances, not endpoints
        healthy_instances_count = sum(1 for is_healthy in instance_health_status.values() if is_healthy)
        unhealthy_instances_count = len(instances) - healthy_instances_count
        
        # Determine overall status
        if healthy_instances_count > 0:
            overall_status = ServiceStatus.HEALTHY
        elif unhealthy_instances_count > 0:
            overall_status = ServiceStatus.UNHEALTHY
        else:
            overall_status = ServiceStatus.UNKNOWN

        return AggregatedHealthResult(
            service_name=service_name,
            overall_status=overall_status,
            total_instances=len(instances),
            healthy_instances=healthy_instances_count,
            unhealthy_instances=unhealthy_instances_count,
            check_results=check_results,
        )

    async def monitor_all_services(
        self,
        get_service_instances_func,
        additional_endpoints: Optional[List[str]] = None,
    ) -> List[AggregatedHealthResult]:
        """
        Monitor health of all registered services.

        Args:
            get_service_instances_func: Function to get instances for a service name
            additional_endpoints: Additional endpoints to check per service

        Returns:
            List of aggregated health results for all services
        """
        # Get all registered services
        services = await self.repository.list_services()
        results = []

        # Check each service
        for service in services:
            try:
                instances = await get_service_instances_func(service.service_name)
                if not instances:
                    # No instances found, mark as unknown
                    results.append(
                        AggregatedHealthResult(
                            service_name=service.service_name,
                            overall_status=ServiceStatus.UNKNOWN,
                            total_instances=0,
                            healthy_instances=0,
                            unhealthy_instances=0,
                            check_results=[],
                        )
                    )
                    continue

                # Perform health check
                aggregated_result = await self.check_service_health(
                    service.service_name,
                    instances,
                    additional_endpoints,
                )
                results.append(aggregated_result)

                # Update service status in database
                await self.repository.update_service_status(
                    service.service_name,
                    aggregated_result.overall_status.value,
                    datetime.now(timezone.utc),
                )

                logger.info(
                    f"Health check for {service.service_name}: {aggregated_result.overall_status.value} "
                    f"({aggregated_result.healthy_instances}/{aggregated_result.total_instances} healthy)"
                )

            except Exception as e:
                logger.error(f"Error checking health for {service.service_name}: {e}")
                # Mark as unknown on error
                results.append(
                    AggregatedHealthResult(
                        service_name=service.service_name,
                        overall_status=ServiceStatus.UNKNOWN,
                        total_instances=0,
                        healthy_instances=0,
                        unhealthy_instances=0,
                        check_results=[],
                    )
                )

        return results

