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
from utils.vault_client import VaultClient


logger = logging.getLogger(__name__)

# Placeholder value stored in PostgreSQL when actual value is in Vault
VAULT_PLACEHOLDER = "VAULT_STORED"


class ConfigurationService:
    def __init__(
        self,
        repository: ConfigRepository,
        redis_client: Redis,
        kafka_producer: Optional[AIOKafkaProducer],
        kafka_topic: str,
        vault_client: Optional[VaultClient] = None,
        cache_ttl: int = 300,
    ):
        self.repository = repository
        self.redis = redis_client
        self.kafka = kafka_producer
        self.kafka_topic = kafka_topic
        self.vault_client = vault_client
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
        # If encrypted and Vault is available, store value in Vault
        value_to_store = req.value
        if req.is_encrypted and self.vault_client and self.vault_client.is_connected():
            # Store actual value in Vault
            vault_success = self.vault_client.write_secret(
                environment=req.environment,
                service_name=req.service_name,
                key=req.key,
                value=req.value,
                metadata={"changed_by": changed_by} if changed_by else None,
            )
            if vault_success:
                # Store placeholder in PostgreSQL
                value_to_store = VAULT_PLACEHOLDER
            else:
                logger.warning(
                    f"Failed to write encrypted config to Vault for {req.key}, "
                    f"storing in PostgreSQL instead (not recommended for sensitive data)"
                )
        
        cfg = await self.repository.create_configuration(
            key=req.key,
            value=value_to_store,
            environment=req.environment,
            service_name=req.service_name,
            is_encrypted=req.is_encrypted,
            changed_by=changed_by,
        )
        
        # Invalidate cache
        await self.redis.delete(self._cache_key(cfg.environment, cfg.service_name, cfg.key))
        
        # Publish event
        await self._publish({
            "event_type": "CONFIG_CREATED",
            "key": cfg.key,
            "environment": cfg.environment,
            "service_name": cfg.service_name,
        })
        
        # For response, return actual value if not encrypted, or fetch from Vault if encrypted
        response_value = cfg.value
        if cfg.is_encrypted and self.vault_client and self.vault_client.is_connected():
            vault_value = self.vault_client.read_secret(
                environment=cfg.environment,
                service_name=cfg.service_name,
                key=cfg.key,
            )
            if vault_value:
                response_value = vault_value
        
        return ConfigurationResponse(
            id=cfg.id,
            key=cfg.key,
            value=response_value,
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
                # For encrypted configs, don't cache the actual value from Vault
                # Only cache if it's not encrypted or if Vault is not available
                cached_resp = ConfigurationResponse(**data)
                if not cached_resp.is_encrypted or not self.vault_client or not self.vault_client.is_connected():
                    return cached_resp
            except Exception:
                pass
        
        cfg = await self.repository.get_configuration(key, environment, service_name)
        if not cfg:
            return None
        
        # If encrypted and Vault is available, fetch actual value from Vault
        value = cfg.value
        if cfg.is_encrypted and self.vault_client and self.vault_client.is_connected():
            if cfg.value == VAULT_PLACEHOLDER:
                # Value is stored in Vault, fetch it
                vault_value = self.vault_client.read_secret(
                    environment=cfg.environment,
                    service_name=cfg.service_name,
                    key=cfg.key,
                )
                if vault_value:
                    value = vault_value
                else:
                    logger.warning(
                        f"Encrypted config {key} marked as stored in Vault but not found. "
                        f"Returning placeholder."
                    )
        
        resp = ConfigurationResponse(
            id=cfg.id,
            key=cfg.key,
            value=value,
            environment=cfg.environment,
            service_name=cfg.service_name,
            is_encrypted=cfg.is_encrypted,
            version=cfg.version,
            created_at=str(cfg.created_at),
            updated_at=str(cfg.updated_at),
        )
        
        # Only cache non-encrypted configs or if Vault is not available
        # Encrypted configs should always be fetched fresh from Vault
        if not cfg.is_encrypted or not self.vault_client or not self.vault_client.is_connected():
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
        resp = []
        for i in items:
            # If encrypted and Vault is available, fetch actual value from Vault
            value = i.value
            if i.is_encrypted and self.vault_client and self.vault_client.is_connected():
                if i.value == VAULT_PLACEHOLDER:
                    vault_value = self.vault_client.read_secret(
                        environment=i.environment,
                        service_name=i.service_name,
                        key=i.key,
                    )
                    if vault_value:
                        value = vault_value
            
            resp.append(
                ConfigurationResponse(
                    id=i.id,
                    key=i.key,
                    value=value,
                    environment=i.environment,
                    service_name=i.service_name,
                    is_encrypted=i.is_encrypted,
                    version=i.version,
                    created_at=str(i.created_at),
                    updated_at=str(i.updated_at),
                )
            )
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
        # Get existing config to check if it was encrypted
        existing_cfg = await self.repository.get_configuration(key, environment, service_name)
        if not existing_cfg:
            return None
        
        # Determine if this should be encrypted (use existing value if not specified)
        should_be_encrypted = is_encrypted if is_encrypted is not None else existing_cfg.is_encrypted
        
        # If encrypted and Vault is available, store value in Vault
        value_to_store = value
        if should_be_encrypted and self.vault_client and self.vault_client.is_connected():
            # Store actual value in Vault
            vault_success = self.vault_client.write_secret(
                environment=environment,
                service_name=service_name,
                key=key,
                value=value,
                metadata={"changed_by": changed_by} if changed_by else None,
            )
            if vault_success:
                # Store placeholder in PostgreSQL
                value_to_store = VAULT_PLACEHOLDER
            else:
                logger.warning(
                    f"Failed to write encrypted config to Vault for {key}, "
                    f"storing in PostgreSQL instead (not recommended for sensitive data)"
                )
        elif existing_cfg.is_encrypted and not should_be_encrypted:
            # Config was encrypted but is being changed to non-encrypted
            # Delete from Vault if it exists
            if self.vault_client and self.vault_client.is_connected():
                self.vault_client.delete_secret(environment, service_name, key)
        elif existing_cfg.is_encrypted and should_be_encrypted:
            # Config was encrypted and remains encrypted, but value changed
            # Vault write above will handle it
            pass
        
        cfg = await self.repository.update_configuration(
            key, environment, service_name, value_to_store, is_encrypted, changed_by
        )
        if not cfg:
            return None
        
        # Invalidate cache
        await self.redis.delete(self._cache_key(environment, service_name, key))
        
        # Publish event
        await self._publish({
            "event_type": "CONFIG_UPDATED",
            "key": key,
            "environment": environment,
            "service_name": service_name,
        })
        
        # For response, return actual value if not encrypted, or fetch from Vault if encrypted
        response_value = cfg.value
        if cfg.is_encrypted and self.vault_client and self.vault_client.is_connected():
            vault_value = self.vault_client.read_secret(
                environment=cfg.environment,
                service_name=cfg.service_name,
                key=cfg.key,
            )
            if vault_value:
                response_value = vault_value
        
        return ConfigurationResponse(
            id=cfg.id,
            key=cfg.key,
            value=response_value,
            environment=cfg.environment,
            service_name=cfg.service_name,
            is_encrypted=cfg.is_encrypted,
            version=cfg.version,
            created_at=str(cfg.created_at),
            updated_at=str(cfg.updated_at),
        )

    async def delete_configuration(self, key: str, environment: str, service_name: str) -> bool:
        # Check if config exists and is encrypted before deleting
        existing_cfg = await self.repository.get_configuration(key, environment, service_name)
        if existing_cfg and existing_cfg.is_encrypted:
            # Delete from Vault if it exists
            if self.vault_client and self.vault_client.is_connected():
                self.vault_client.delete_secret(environment, service_name, key)
        
        ok = await self.repository.delete_configuration(key, environment, service_name)
        
        # Invalidate cache
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


