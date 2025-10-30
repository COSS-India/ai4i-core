import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

from redis.asyncio import Redis

from models.service_registry_models import ServiceInstance, ServiceStatus
from registry.base import ServiceRegistryClient
from repositories.service_registry_repository import ServiceRegistryRepository


logger = logging.getLogger(__name__)


class ServiceRegistryService:
    def __init__(
        self,
        registry_client: ServiceRegistryClient,
        repository: ServiceRegistryRepository,
        redis_client: Redis,
        cache_ttl: int = 60,
    ) -> None:
        self.registry = registry_client
        self.repository = repository
        self.redis = redis_client
        self.cache_ttl = cache_ttl

    def _instances_cache_key(self, service_name: str) -> str:
        return f"registry:instances:{service_name}"

    async def register_service(self, service_name: str, service_url: str, health_check_url: Optional[str], service_metadata: Dict[str, Any]) -> str:
        instance_id = await self.registry.register_service(service_name, service_url, {"health_check_url": health_check_url, **service_metadata})
        await self.repository.register_service(service_name, service_url, health_check_url, ServiceStatus.HEALTHY.value, service_metadata)
        await self.redis.delete(self._instances_cache_key(service_name))
        return instance_id

    async def deregister_service(self, service_name: str, instance_id: str) -> None:
        await self.registry.deregister_service(service_name, instance_id)
        await self.repository.update_service_status(service_name, ServiceStatus.UNKNOWN.value)
        await self.redis.delete(self._instances_cache_key(service_name))

    async def get_service_instances(self, service_name: str) -> List[ServiceInstance]:
        ck = self._instances_cache_key(service_name)
        cached = await self.redis.get(ck)
        if cached:
            try:
                data = [ServiceInstance(**i) for i in __import__("json").loads(cached)]
                return data
            except Exception:
                pass
        raw_instances = await self.registry.get_service_instances(service_name)
        instances = [
            ServiceInstance(
                instance_id=i.get("instance_id"),
                service_name=service_name,
                service_url=i.get("service_url"),
                health_check_url=i.get("health_check_url"),
                status=ServiceStatus(i.get("status", ServiceStatus.UNKNOWN.value)),
                service_metadata=i,
            )
            for i in raw_instances
        ]
        await self.redis.set(ck, __import__("json").dumps([i.model_dump() for i in instances]), ex=self.cache_ttl)
        return instances

    async def get_service_url(self, service_name: str) -> Optional[str]:
        instances = [i for i in await self.get_service_instances(service_name) if i.status == ServiceStatus.HEALTHY]
        if not instances:
            return None
        return random.choice(instances).service_url

    async def list_all_services(self) -> List[ServiceInstance]:
        rows = await self.repository.list_services()
        return [
            ServiceInstance(
                service_name=r.service_name,
                service_url=r.service_url,
                health_check_url=r.health_check_url,
                status=ServiceStatus(r.status if r.status in ServiceStatus._value2member_map_ else ServiceStatus.UNKNOWN.value),
                service_metadata=r.service_metadata or {},
                registered_at=str(r.registered_at) if r.registered_at else None,
            )
            for r in rows
        ]

    async def perform_health_check(self, service_name: str, timeout: float = 3.0) -> ServiceStatus:
        instances = await self.get_service_instances(service_name)
        status = ServiceStatus.UNKNOWN
        for inst in instances:
            url = inst.health_check_url or inst.service_url
            ok = await self._http_health_ok(url, timeout)
            if ok:
                status = ServiceStatus.HEALTHY
                break
        await self.repository.update_service_status(service_name, status.value)
        return status

    async def _http_health_ok(self, url: str, timeout: float) -> bool:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as resp:
                    return resp.status < 500
        except Exception:
            return False

    async def watch_service_changes(self, service_name: str) -> None:
        async def _on_change(instances: List[dict]):
            await self.redis.delete(self._instances_cache_key(service_name))
        await self.registry.watch_service(service_name, _on_change)

    async def sync_registry(self) -> None:
        # Placeholder for sync logic; can iterate all services and reconcile
        pass


