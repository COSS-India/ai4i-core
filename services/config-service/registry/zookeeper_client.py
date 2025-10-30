import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Awaitable, Callable

from registry.base import ServiceRegistryClient

try:
    from kazoo.client import KazooClient
    from kazoo.retry import KazooRetry
    from kazoo.exceptions import NoNodeError
except Exception:  # pragma: no cover - optional import until installed
    KazooClient = None  # type: ignore
    KazooRetry = None  # type: ignore
    NoNodeError = Exception  # type: ignore


logger = logging.getLogger(__name__)


class ZooKeeperRegistryClient(ServiceRegistryClient):
    def __init__(self) -> None:
        self._hosts = os.getenv("ZOOKEEPER_HOSTS", "zookeeper:2181")
        self._base_path = os.getenv("ZOOKEEPER_BASE_PATH", "/services")
        self._conn_timeout = float(os.getenv("ZOOKEEPER_CONNECTION_TIMEOUT", "10"))
        self._session_timeout = float(os.getenv("ZOOKEEPER_SESSION_TIMEOUT", "30"))
        self._client: Optional[KazooClient] = None
        self._retry = KazooRetry(max_tries=3, delay=0.5) if KazooRetry else None
        self._instance_nodes: Dict[str, str] = {}

    async def connect(self) -> None:
        if not KazooClient:
            logger.warning("Kazoo is not installed; ZooKeeper client disabled")
            return
        loop = asyncio.get_running_loop()
        self._client = KazooClient(
            hosts=self._hosts,
            timeout=self._session_timeout,
            connection_retry=self._retry,
            command_retry=self._retry,
        )
        await loop.run_in_executor(None, self._client.start)
        await loop.run_in_executor(None, self._ensure_path, self._base_path)
        logger.info("Connected to ZooKeeper at %s", self._hosts)

    def _ensure_path(self, path: str) -> None:
        assert self._client is not None
        self._client.ensure_path(path)

    async def disconnect(self) -> None:
        if self._client:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._client.stop)
            await loop.run_in_executor(None, self._client.close)
            logger.info("Disconnected from ZooKeeper")
        self._client = None

    async def register_service(self, service_name: str, service_url: str, service_metadata: Dict[str, Any]) -> str:
        if not self._client:
            return ""
        loop = asyncio.get_running_loop()
        service_path = f"{self._base_path}/{service_name}/instances"
        await loop.run_in_executor(None, self._ensure_path, service_path)
        instance_id = service_metadata.get("instance_id") or str(uuid.uuid4())
        node_path = f"{service_path}/{instance_id}"
        data = json.dumps({"service_url": service_url, **service_metadata}).encode("utf-8")
        def _create():
            assert self._client is not None
            if not self._client.exists(node_path):
                self._client.create(node_path, data, ephemeral=True, makepath=True)
            else:
                self._client.set(node_path, data)
        await loop.run_in_executor(None, _create)
        self._instance_nodes[service_name] = node_path
        return instance_id

    async def deregister_service(self, service_name: str, instance_id: str) -> None:
        if not self._client:
            return
        loop = asyncio.get_running_loop()
        node_path = f"{self._base_path}/{service_name}/instances/{instance_id}"
        def _delete():
            assert self._client is not None
            try:
                self._client.delete(node_path)
            except NoNodeError:
                pass
        await loop.run_in_executor(None, _delete)

    async def get_service_instances(self, service_name: str) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        loop = asyncio.get_running_loop()
        service_path = f"{self._base_path}/{service_name}/instances"
        def _list() -> List[Dict[str, Any]]:
            assert self._client is not None
            if not self._client.exists(service_path):
                return []
            children = self._client.get_children(service_path)
            instances: List[Dict[str, Any]] = []
            for child in children:
                data, _ = self._client.get(f"{service_path}/{child}")
                try:
                    instances.append(json.loads(data.decode("utf-8")))
                except Exception:
                    continue
            return instances
        return await loop.run_in_executor(None, _list)

    async def watch_service(self, service_name: str, callback: Callable[[List[Dict[str, Any]]], Awaitable[None]]) -> None:
        if not self._client:
            return
        service_path = f"{self._base_path}/{service_name}/instances"
        loop = asyncio.get_running_loop()

        def _on_change(children):  # kazoo ChildrenWatch callback (sync)
            async def _invoke():
                instances = await self.get_service_instances(service_name)
                await callback(instances)
            asyncio.run_coroutine_threadsafe(_invoke(), loop)

        assert self._client is not None
        self._client.ensure_path(service_path)
        from kazoo.recipe.watchers import ChildrenWatch  # type: ignore
        ChildrenWatch(self._client, service_path, func=_on_change)

    async def health_check(self) -> bool:
        if not self._client:
            return False
        loop = asyncio.get_running_loop()
        def _ping() -> bool:
            assert self._client is not None
            try:
                self._client.get_children("/")
                return True
            except Exception:
                return False
        return await loop.run_in_executor(None, _ping)


