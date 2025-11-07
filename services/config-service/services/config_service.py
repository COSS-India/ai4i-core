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
        # Store ALL configs in Vault (single source of truth)
        if not self.vault_client or not self.vault_client.is_connected():
            raise ValueError(
                "Cannot create configuration: Vault is not available. "
                "Please configure VAULT_ADDR and VAULT_TOKEN."
            )
        
        # Store value in Vault (both encrypted and non-encrypted)
        vault_success = self.vault_client.write_secret(
            environment=req.environment,
            service_name=req.service_name,
            key=req.key,
            value=req.value,
            is_encrypted=req.is_encrypted,
            metadata={"changed_by": changed_by} if changed_by else None,
        )
        
        if not vault_success:
            raise RuntimeError(f"Failed to write config to Vault for {req.key}")
        
        # Invalidate cache
        await self.redis.delete(self._cache_key(req.environment, req.service_name, req.key))
        
        # Publish event
        await self._publish({
            "event_type": "CONFIG_CREATED",
            "key": req.key,
            "environment": req.environment,
            "service_name": req.service_name,
        })
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        return ConfigurationResponse(
            id=None,  # No database ID for Vault-stored configs (excluded from response)
            key=req.key,
            value=req.value,
            environment=req.environment,
            service_name=req.service_name,
            is_encrypted=req.is_encrypted,
            version=1,
            created_at=str(now),
            updated_at=str(now),
        )

    async def get_configuration(self, key: str, environment: str, service_name: str) -> Optional[ConfigurationResponse]:
        # All configs are stored in Vault
        if not self.vault_client or not self.vault_client.is_connected():
            return None
        
        secret_data = self.vault_client.read_secret(
            environment=environment,
            service_name=service_name,
            key=key,
        )
        
        if not secret_data:
            return None
        
        # Check cache for non-encrypted configs
        if not secret_data.get("is_encrypted", False):
            ck = self._cache_key(environment, service_name, key)
            cached = await self.redis.get(ck)
            if cached:
                try:
                    data = json.loads(cached)
                    return ConfigurationResponse(**data)
                except Exception:
                    pass
        
        # Build response from Vault data
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        # Get timestamps from Vault metadata if available
        vault_metadata = secret_data.get("metadata", {})
        created_at = vault_metadata.get("created_time", str(now))
        updated_at = vault_metadata.get("updated_time", str(now))
        
        resp = ConfigurationResponse(
            id=None,  # No database ID for Vault-stored configs (excluded from response)
            key=key,
            value=secret_data.get("value"),
            environment=environment,
            service_name=service_name,
            is_encrypted=secret_data.get("is_encrypted", False),
            version=1,  # Vault KV v2 tracks versions internally
            created_at=created_at,
            updated_at=updated_at,
        )
        
        # Cache non-encrypted configs only
        if not secret_data.get("is_encrypted", False):
            ck = self._cache_key(environment, service_name, key)
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
        # All configs are stored in Vault
        if not self.vault_client or not self.vault_client.is_connected():
            return [], 0
        
        if not environment or not service_name:
            return [], 0
        
        resp = []
        
        try:
            # List all secrets from Vault for the given environment and service
            vault_keys = self.vault_client.list_secrets(
                environment=environment,
                service_name=service_name,
            )
            
            # Filter by keys if specified
            if keys:
                vault_keys = [k for k in vault_keys if k in keys]
            
            # Fetch values for each key
            for vault_key in vault_keys:
                secret_data = self.vault_client.read_secret(
                    environment=environment,
                    service_name=service_name,
                    key=vault_key,
                )
                
                if secret_data:
                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc)
                    
                    # Get timestamps from Vault metadata if available
                    vault_metadata = secret_data.get("metadata", {})
                    created_at = vault_metadata.get("created_time", str(now))
                    updated_at = vault_metadata.get("updated_time", str(now))
                    
                    resp.append(
                        ConfigurationResponse(
                            id=None,
                            key=vault_key,
                            value=secret_data.get("value"),
                            environment=environment,
                            service_name=service_name,
                            is_encrypted=secret_data.get("is_encrypted", False),
                            version=1,
                            created_at=created_at,
                            updated_at=updated_at,
                        )
                    )
        except Exception as e:
            logger.warning(f"Error fetching configs from Vault: {e}")
        
        # Apply pagination
        total = len(resp)
        resp = resp[offset:offset + limit]
        
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
        # All configs are stored in Vault
        if not self.vault_client or not self.vault_client.is_connected():
            raise ValueError(
                "Cannot update configuration: Vault is not available. "
                "Please configure VAULT_ADDR and VAULT_TOKEN."
            )
        
        # Check if config exists to determine is_encrypted if not specified
        existing_data = self.vault_client.read_secret(environment, service_name, key)
        if not existing_data:
            return None  # Config doesn't exist
        
        # Determine if this should be encrypted
        should_be_encrypted = is_encrypted if is_encrypted is not None else existing_data.get("is_encrypted", False)
        
        # Update in Vault
        vault_success = self.vault_client.write_secret(
            environment=environment,
            service_name=service_name,
            key=key,
            value=value,
            is_encrypted=should_be_encrypted,
            metadata={"changed_by": changed_by} if changed_by else None,
        )
        
        if not vault_success:
            raise RuntimeError(f"Failed to update config in Vault for {key}")
        
        # Invalidate cache
        await self.redis.delete(self._cache_key(environment, service_name, key))
        
        # Publish event
        await self._publish({
            "event_type": "CONFIG_UPDATED",
            "key": key,
            "environment": environment,
            "service_name": service_name,
        })
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        return ConfigurationResponse(
            id=0,
            key=key,
            value=value,
            environment=environment,
            service_name=service_name,
            is_encrypted=should_be_encrypted,
            version=1,
            created_at=str(now),
            updated_at=str(now),
        )

    async def delete_configuration(self, key: str, environment: str, service_name: str) -> bool:
        # All configs are stored in Vault
        if not self.vault_client or not self.vault_client.is_connected():
            return False
        
        deleted = self.vault_client.delete_secret(environment, service_name, key)
        
        # Invalidate cache
        await self.redis.delete(self._cache_key(environment, service_name, key))
        
        if deleted:
            await self._publish({
                "event_type": "CONFIG_DELETED",
                "key": key,
                "environment": environment,
                "service_name": service_name,
            })
        
        return deleted

    async def get_configuration_history(self, configuration_id: int):
        # History is available through Vault KV v2 versioning
        # For now, return empty list as we need to implement Vault version history
        # TODO: Implement Vault version history retrieval
        return []

    async def bulk_get_configurations(self, environment: str, service_name: str, keys: List[str]) -> Dict[str, Optional[ConfigurationResponse]]:
        result: Dict[str, Optional[ConfigurationResponse]] = {}
        for k in keys:
            result[k] = await self.get_configuration(k, environment, service_name)
        return result


