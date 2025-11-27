import abc
from typing import Any, Awaitable, Callable, Dict, List, Optional


class ServiceRegistryClient(abc.ABC):
    @abc.abstractmethod
    async def connect(self) -> None:  # pragma: no cover - interface only
        ...

    @abc.abstractmethod
    async def disconnect(self) -> None:  # pragma: no cover - interface only
        ...

    @abc.abstractmethod
    async def register_service(self, service_name: str, service_url: str, service_metadata: Dict[str, Any]) -> str:
        """Register a service instance. Returns instance_id."""
        ...

    @abc.abstractmethod
    async def deregister_service(self, service_name: str, instance_id: str) -> None:
        ...

    @abc.abstractmethod
    async def get_service_instances(self, service_name: str) -> List[Dict[str, Any]]:
        ...

    @abc.abstractmethod
    async def watch_service(self, service_name: str, callback: Callable[[List[Dict[str, Any]]], Awaitable[None]]) -> None:
        ...

    @abc.abstractmethod
    async def health_check(self) -> bool:
        ...


