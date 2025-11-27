import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from aiokafka import AIOKafkaProducer
from redis.asyncio import Redis

from models.config_models import (
    ConfigurationCreate,
    ConfigurationListResponse,
    ConfigurationQuery,
    ConfigurationResponse,
    ConfigurationUpdate,
)
from repositories.config_repository import ConfigRepository


logger = logging.getLogger(__name__)


class ConfigurationService:
    def __init__(self, repository: ConfigRepository, redis_client: Redis, kafka_producer: Optional[AIOKafkaProducer], kafka_topic: str, cache_ttl: int = 300):
        self.repository = repository
        self.redis = redis_client
        self.kafka = kafka_producer
        self.kafka_topic = kafka_topic
        self.cache_ttl = cache_ttl

    def _cache_key(self, environment: str, service_name: str, key: str) -> str:
        return f"config:{environment}:{service_name}:{key}"

    async def _publish(self, payload: Dict[str, Any]) -> None:
        if not self.kafka:
            return
        try:
            await self.kafka.send_and_wait(self.kafka_topic, json.dumps(payload).encode("utf-8"))
        except Exception as e:
            logger.warning(f"Failed to publish Kafka event: {e}")

    async def create_configuration(self, req: ConfigurationCreate, changed_by: Optional[str] = None) -> ConfigurationResponse:
        cfg = await self.repository.create_configuration(
            key=req.key,
            value=req.value,
            environment=req.environment,
            service_name=req.service_name,
            is_encrypted=req.is_encrypted,
            changed_by=changed_by,
        )
        await self.redis.delete(self._cache_key(cfg.environment, cfg.service_name, cfg.key))
        await self._publish({
            "event_type": "CONFIG_CREATED",
            "key": cfg.key,
            "environment": cfg.environment,
            "service_name": cfg.service_name,
        })
        return ConfigurationResponse(
            id=cfg.id,
            key=cfg.key,
            value=cfg.value,
            environment=cfg.environment,
            service_name=cfg.service_name,
            is_encrypted=cfg.is_encrypted,
            version=cfg.version,
            created_at=str(cfg.created_at),
            updated_at=str(cfg.updated_at),
        )

    async def get_configuration(self, key: str, environment: str, service_name: str) -> Optional[ConfigurationResponse]:
        ck = self._cache_key(environment, service_name, key)
        cached = await self.redis.get(ck)
        if cached:
            try:
                data = json.loads(cached)
                return ConfigurationResponse(**data)
            except Exception:
                pass
        cfg = await self.repository.get_configuration(key, environment, service_name)
        if not cfg:
            return None
        resp = ConfigurationResponse(
            id=cfg.id,
            key=cfg.key,
            value=cfg.value,
            environment=cfg.environment,
            service_name=cfg.service_name,
            is_encrypted=cfg.is_encrypted,
            version=cfg.version,
            created_at=str(cfg.created_at),
            updated_at=str(cfg.updated_at),
        )
        await self.redis.set(ck, json.dumps(resp.model_dump()), ex=self.cache_ttl)
        return resp

    async def get_configurations(
        self,
        environment: Optional[str],
        service_name: Optional[str],
        keys: Optional[List[str]],
        limit: int,
        offset: int,
    ) -> Tuple[List[ConfigurationResponse], int]:
        items, total = await self.repository.get_configurations(environment, service_name, keys, limit, offset)
        resp = [
            ConfigurationResponse(
                id=i.id,
                key=i.key,
                value=i.value,
                environment=i.environment,
                service_name=i.service_name,
                is_encrypted=i.is_encrypted,
                version=i.version,
                created_at=str(i.created_at),
                updated_at=str(i.updated_at),
            )
            for i in items
        ]
        return resp, total

    async def update_configuration(
        self,
        key: str,
        environment: str,
        service_name: str,
        value: str,
        is_encrypted: Optional[bool],
        changed_by: Optional[str] = None,
    ) -> Optional[ConfigurationResponse]:
        cfg = await self.repository.update_configuration(key, environment, service_name, value, is_encrypted, changed_by)
        if not cfg:
            return None
        await self.redis.delete(self._cache_key(environment, service_name, key))
        await self._publish({
            "event_type": "CONFIG_UPDATED",
            "key": key,
            "environment": environment,
            "service_name": service_name,
        })
        return ConfigurationResponse(
            id=cfg.id,
            key=cfg.key,
            value=cfg.value,
            environment=cfg.environment,
            service_name=cfg.service_name,
            is_encrypted=cfg.is_encrypted,
            version=cfg.version,
            created_at=str(cfg.created_at),
            updated_at=str(cfg.updated_at),
        )

    async def delete_configuration(self, key: str, environment: str, service_name: str) -> bool:
        ok = await self.repository.delete_configuration(key, environment, service_name)
        await self.redis.delete(self._cache_key(environment, service_name, key))
        if ok:
            await self._publish({
                "event_type": "CONFIG_DELETED",
                "key": key,
                "environment": environment,
                "service_name": service_name,
            })
        return ok

    async def get_configuration_history(self, configuration_id: int):
        return await self.repository.get_configuration_history(configuration_id)

    async def bulk_get_configurations(self, environment: str, service_name: str, keys: List[str]) -> Dict[str, Optional[ConfigurationResponse]]:
        result: Dict[str, Optional[ConfigurationResponse]] = {}
        for k in keys:
            result[k] = await self.get_configuration(k, environment, service_name)
        return result


