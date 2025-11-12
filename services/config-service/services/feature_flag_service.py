"""
Business logic service for feature flags
"""
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiokafka import AIOKafkaProducer
from openfeature import api as openfeature_api
from openfeature.evaluation_context import EvaluationContext
from redis.asyncio import Redis

from models.feature_flag_models import (
    BulkEvaluationRequest,
    FeatureFlagCreate,
    FeatureFlagEvaluationRequest,
    FeatureFlagEvaluationResponse,
    FeatureFlagListResponse,
    FeatureFlagResponse,
)
from repositories.feature_flag_repository import FeatureFlagRepository

logger = logging.getLogger(__name__)


class FeatureFlagService:
    def __init__(
        self,
        repository: FeatureFlagRepository,
        redis_client: Redis,
        kafka_producer: Optional[AIOKafkaProducer],
        openfeature_client,
        kafka_topic: str,
        cache_ttl: int = 300,
        unleash_url: Optional[str] = None,
        unleash_api_token: Optional[str] = None,
    ):
        self.repository = repository
        self.redis = redis_client
        self.kafka = kafka_producer
        self.openfeature_client = openfeature_client
        self.kafka_topic = kafka_topic
        self.cache_ttl = cache_ttl
        self.unleash_url = unleash_url
        self.unleash_api_token = unleash_api_token

    def _cache_key(self, environment: str, flag_name: str, user_id: Optional[str], context: Optional[dict] = None) -> str:
        """Generate cache key for flag evaluation with context hash"""
        user_part = user_id or "anonymous"
        
        # Hash context attributes for cache key
        context_hash = None
        if context:
            try:
                # Sort keys for consistent hashing
                context_json = json.dumps(context, sort_keys=True)
                context_hash = hashlib.sha256(context_json.encode('utf-8')).hexdigest()[:16]  # Use first 16 chars
            except Exception as e:
                logger.warning(f"Failed to hash context for cache key: {e}")
        
        context_part = f":{context_hash}" if context_hash else ""
        return f"feature_flag:eval:{environment}:{flag_name}:{user_part}{context_part}"
    
    async def _invalidate_cache(self, environment: str, flag_name: str) -> None:
        """Invalidate cache keys matching pattern for a flag"""
        try:
            pattern = f"feature_flag:eval:{environment}:{flag_name}:*"
            cursor = 0
            deleted_count = 0
            
            while True:
                # Use SCAN to find matching keys
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                
                if keys:
                    # Delete all matching keys
                    deleted = await self.redis.delete(*keys)
                    deleted_count += deleted
                
                # If cursor is 0, we've scanned all keys
                if cursor == 0:
                    break
            
            if deleted_count > 0:
                logger.info(f"Invalidated {deleted_count} cache keys for flag {flag_name} in {environment}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for flag {flag_name} in {environment}: {e}", exc_info=True)

    async def _publish(self, payload: Dict[str, Any]) -> None:
        """Publish event to Kafka"""
        if not self.kafka:
            return
        try:
            await self.kafka.send_and_wait(self.kafka_topic, json.dumps(payload).encode("utf-8"))
        except Exception as e:
            logger.warning(f"Failed to publish Kafka event: {e}")

    def _build_evaluation_context(self, user_id: Optional[str], context: dict) -> EvaluationContext:
        """Build OpenFeature EvaluationContext from user_id and context"""
        return EvaluationContext(
            targeting_key=user_id,
            attributes=context or {},
        )

    async def evaluate_flag(
        self,
        flag_name: str,
        user_id: Optional[str],
        context: dict,
        default_value: Any,
        environment: str,
    ) -> FeatureFlagEvaluationResponse:
        """Evaluate a feature flag and return detailed response"""
        cache_key = self._cache_key(environment, flag_name, user_id, context)
        
        # Check cache first
        cached = await self.redis.get(cache_key)
        if cached:
            try:
                # Decode bytes to string if needed
                if isinstance(cached, bytes):
                    cached = cached.decode('utf-8')
                data = json.loads(cached)
                return FeatureFlagEvaluationResponse(**data)
            except Exception:
                pass

        # Evaluate using OpenFeature
        eval_context = self._build_evaluation_context(user_id, context)
        value = default_value
        reason = "ERROR"
        variant = None

        try:
            if self.openfeature_client:
                # Determine type and evaluate
                if isinstance(default_value, bool):
                    details = self.openfeature_client.get_boolean_details(flag_name, default_value, eval_context)
                    value = details.value
                    reason = details.reason
                elif isinstance(default_value, str):
                    details = self.openfeature_client.get_string_details(flag_name, default_value, eval_context)
                    value = details.value
                    reason = details.reason
                    # Get variant from details if available, otherwise infer from value
                    variant = getattr(details, 'variant', None)
                    if variant is None and value != default_value:
                        variant = str(value)
                elif isinstance(default_value, int):
                    details = self.openfeature_client.get_integer_details(flag_name, default_value, eval_context)
                    value = details.value
                    reason = details.reason
                elif isinstance(default_value, float):
                    details = self.openfeature_client.get_float_details(flag_name, default_value, eval_context)
                    value = details.value
                    reason = details.reason
                elif isinstance(default_value, dict):
                    details = self.openfeature_client.get_object_details(flag_name, default_value, eval_context)
                    value = details.value
                    reason = details.reason
                    # Get variant from details if available
                    variant = getattr(details, 'variant', None)
            else:
                logger.warning("OpenFeature client not available, using default value")
        except Exception as e:
            logger.error(f"Error evaluating flag {flag_name}: {e}", exc_info=True)
            value = default_value
            reason = "ERROR"

        # Record evaluation
        try:
            # For boolean types, store in result; for others, store in evaluated_value
            result_value = None
            evaluated_value_json = None
            if isinstance(value, bool):
                result_value = value
            else:
                # Store non-boolean values in evaluated_value as JSON
                evaluated_value_json = value
            
            await self.repository.record_evaluation(
                flag_name=flag_name,
                user_id=user_id,
                context=context or {},
                result=result_value,
                variant=variant,
                environment=environment,
                reason=reason,
                evaluated_value=evaluated_value_json,
            )
        except Exception as e:
            logger.warning(f"Failed to record evaluation: {e}")

        # Cache result
        from datetime import datetime
        response = FeatureFlagEvaluationResponse(
            flag_name=flag_name,
            value=value,
            variant=variant,
            reason=reason,
            evaluated_at=datetime.utcnow().isoformat(),
        )
        await self.redis.set(cache_key, json.dumps(response.model_dump()), ex=self.cache_ttl)

        # Publish event
        await self._publish({
            "event_type": "FEATURE_FLAG_EVALUATED",
            "flag_name": flag_name,
            "user_id": user_id,
            "environment": environment,
            "value": str(value),
            "reason": reason,
        })

        return response

    async def evaluate_boolean_flag(
        self,
        flag_name: str,
        user_id: Optional[str],
        context: dict,
        default_value: bool,
        environment: str,
    ) -> Tuple[bool, str]:
        """Evaluate boolean flag and return (value, reason) tuple"""
        eval_context = self._build_evaluation_context(user_id, context)
        
        try:
            if self.openfeature_client:
                details = self.openfeature_client.get_boolean_details(flag_name, default_value, eval_context)
                result = details.value
                reason = details.reason
            else:
                result = default_value
                reason = "ERROR"
        except Exception as e:
            logger.error(f"Error evaluating boolean flag {flag_name}: {e}", exc_info=True)
            result = default_value
            reason = "ERROR"

        # Record evaluation
        try:
            await self.repository.record_evaluation(
                flag_name=flag_name,
                user_id=user_id,
                context=context or {},
                result=result,
                variant=None,
                environment=environment,
                reason=reason,
                evaluated_value=None,  # Boolean values stored in result
            )
        except Exception as e:
            logger.warning(f"Failed to record evaluation: {e}")

        return result, reason

    async def evaluate_string_flag(
        self,
        flag_name: str,
        user_id: Optional[str],
        context: dict,
        default_value: str,
        environment: str,
    ) -> str:
        """Evaluate string flag and return string value"""
        eval_context = self._build_evaluation_context(user_id, context)
        
        try:
            if self.openfeature_client:
                details = self.openfeature_client.get_string_details(flag_name, default_value, eval_context)
                return details.value
            else:
                return default_value
        except Exception as e:
            logger.error(f"Error evaluating string flag {flag_name}: {e}", exc_info=True)
            return default_value

    async def evaluate_integer_flag(
        self,
        flag_name: str,
        user_id: Optional[str],
        context: dict,
        default_value: int,
        environment: str,
    ) -> int:
        """Evaluate integer flag and return integer value"""
        eval_context = self._build_evaluation_context(user_id, context)
        
        try:
            if self.openfeature_client:
                details = self.openfeature_client.get_integer_details(flag_name, default_value, eval_context)
                return details.value
            else:
                return default_value
        except Exception as e:
            logger.error(f"Error evaluating integer flag {flag_name}: {e}", exc_info=True)
            return default_value

    async def evaluate_float_flag(
        self,
        flag_name: str,
        user_id: Optional[str],
        context: dict,
        default_value: float,
        environment: str,
    ) -> float:
        """Evaluate float flag and return float value"""
        eval_context = self._build_evaluation_context(user_id, context)
        
        try:
            if self.openfeature_client:
                details = self.openfeature_client.get_float_details(flag_name, default_value, eval_context)
                return details.value
            else:
                return default_value
        except Exception as e:
            logger.error(f"Error evaluating float flag {flag_name}: {e}", exc_info=True)
            return default_value

    async def evaluate_object_flag(
        self,
        flag_name: str,
        user_id: Optional[str],
        context: dict,
        default_value: dict,
        environment: str,
    ) -> dict:
        """Evaluate object flag and return dict value"""
        eval_context = self._build_evaluation_context(user_id, context)
        
        try:
            if self.openfeature_client:
                details = self.openfeature_client.get_object_details(flag_name, default_value, eval_context)
                return details.value
            else:
                return default_value
        except Exception as e:
            logger.error(f"Error evaluating object flag {flag_name}: {e}", exc_info=True)
            return default_value

    async def bulk_evaluate_flags(
        self,
        flag_names: List[str],
        user_id: Optional[str],
        context: dict,
        environment: str,
    ) -> Dict[str, Any]:
        """Evaluate multiple flags in parallel"""
        import asyncio
        
        async def eval_single(flag_name: str):
            try:
                result = await self.evaluate_flag(
                    flag_name=flag_name,
                    user_id=user_id,
                    context=context,
                    default_value=False,  # Default to False for bulk evaluation
                    environment=environment,
                )
                return flag_name, result.model_dump()
            except Exception as e:
                logger.error(f"Error evaluating flag {flag_name} in bulk: {e}")
                return flag_name, {"error": str(e)}

        results = await asyncio.gather(*[eval_single(name) for name in flag_names])
        return {name: result for name, result in results}

    async def create_feature_flag(self, req: FeatureFlagCreate) -> FeatureFlagResponse:
        """Create a new feature flag"""
        flag = await self.repository.create_feature_flag(
            name=req.name,
            description=req.description,
            is_enabled=req.is_enabled,
            environment=req.environment,
            rollout_percentage=req.rollout_percentage,
            target_users=req.target_users,
        )
        
        # Invalidate cache
        await self._invalidate_cache(req.environment, req.name)
        
        # Publish event
        await self._publish({
            "event_type": "FEATURE_FLAG_CREATED",
            "flag_name": req.name,
            "environment": req.environment,
        })
        
        return FeatureFlagResponse(
            id=flag.id,
            name=flag.name,
            description=flag.description,
            is_enabled=flag.is_enabled,
            environment=flag.environment,
            rollout_percentage=flag.rollout_percentage,
            target_users=flag.target_users,
            unleash_flag_name=flag.unleash_flag_name,
            last_synced_at=str(flag.last_synced_at) if flag.last_synced_at else None,
            evaluation_count=flag.evaluation_count or 0,
            last_evaluated_at=str(flag.last_evaluated_at) if flag.last_evaluated_at else None,
            created_at=str(flag.created_at),
            updated_at=str(flag.updated_at),
        )

    async def get_feature_flag(self, name: str, environment: str) -> Optional[FeatureFlagResponse]:
        """Get feature flag by name"""
        flag = await self.repository.get_feature_flag(name, environment)
        if not flag:
            return None
        
        return FeatureFlagResponse(
            id=flag.id,
            name=flag.name,
            description=flag.description,
            is_enabled=flag.is_enabled,
            environment=flag.environment,
            rollout_percentage=flag.rollout_percentage,
            target_users=flag.target_users,
            unleash_flag_name=flag.unleash_flag_name,
            last_synced_at=str(flag.last_synced_at) if flag.last_synced_at else None,
            evaluation_count=flag.evaluation_count or 0,
            last_evaluated_at=str(flag.last_evaluated_at) if flag.last_evaluated_at else None,
            created_at=str(flag.created_at),
            updated_at=str(flag.updated_at),
        )

    async def get_feature_flags(
        self,
        environment: Optional[str],
        limit: int,
        offset: int,
    ) -> Tuple[List[FeatureFlagResponse], int]:
        """Get feature flags with pagination"""
        items, total = await self.repository.get_feature_flags(environment, limit, offset)
        resp = [
            FeatureFlagResponse(
                id=i.id,
                name=i.name,
                description=i.description,
                is_enabled=i.is_enabled,
                environment=i.environment,
                rollout_percentage=i.rollout_percentage,
                target_users=i.target_users,
                unleash_flag_name=i.unleash_flag_name,
                last_synced_at=str(i.last_synced_at) if i.last_synced_at else None,
                evaluation_count=i.evaluation_count or 0,
                last_evaluated_at=str(i.last_evaluated_at) if i.last_evaluated_at else None,
                created_at=str(i.created_at),
                updated_at=str(i.updated_at),
            )
            for i in items
        ]
        return resp, total

    async def update_feature_flag(
        self,
        name: str,
        environment: str,
        **kwargs,
    ) -> Optional[FeatureFlagResponse]:
        """Update feature flag"""
        flag = await self.repository.update_feature_flag(name, environment, **kwargs)
        if not flag:
            return None
        
        # Invalidate cache
        await self._invalidate_cache(environment, name)
        
        # Publish event
        await self._publish({
            "event_type": "FEATURE_FLAG_UPDATED",
            "flag_name": name,
            "environment": environment,
        })
        
        return FeatureFlagResponse(
            id=flag.id,
            name=flag.name,
            description=flag.description,
            is_enabled=flag.is_enabled,
            environment=flag.environment,
            rollout_percentage=flag.rollout_percentage,
            target_users=flag.target_users,
            unleash_flag_name=flag.unleash_flag_name,
            last_synced_at=str(flag.last_synced_at) if flag.last_synced_at else None,
            evaluation_count=flag.evaluation_count or 0,
            last_evaluated_at=str(flag.last_evaluated_at) if flag.last_evaluated_at else None,
            created_at=str(flag.created_at),
            updated_at=str(flag.updated_at),
        )

    async def delete_feature_flag(self, name: str, environment: str) -> bool:
        """Delete feature flag"""
        ok = await self.repository.delete_feature_flag(name, environment)
        
        if ok:
            # Invalidate cache
            await self._invalidate_cache(environment, name)
            
            # Publish event
            await self._publish({
                "event_type": "FEATURE_FLAG_DELETED",
                "flag_name": name,
                "environment": environment,
            })
        
        return ok

    async def sync_flags_from_unleash(self, environment: str) -> int:
        """Sync flags from Unleash Admin API"""
        if not self.unleash_url or not self.unleash_api_token:
            logger.error("Unleash URL or API token not configured for sync")
            return 0
        
        try:
            # Construct Unleash Admin API URL
            base_url = self.unleash_url.rstrip('/api')
            admin_url = f"{base_url}/api/admin/projects/default/features"
            
            headers = {
                "Authorization": self.unleash_api_token,
                "Content-Type": "application/json",
            }
            
            synced_count = 0
            offset = 0
            limit = 100
            
            async with aiohttp.ClientSession() as session:
                while True:
                    # Fetch features with pagination
                    params = {"offset": offset, "limit": limit}
                    async with session.get(admin_url, headers=headers, params=params) as response:
                        if response.status != 200:
                            logger.error(f"Failed to fetch features from Unleash: {response.status}")
                            break
                        
                        data = await response.json()
                        features = data.get("features", [])
                        
                        if not features:
                            break
                        
                        # Process each feature
                        for feature in features:
                            try:
                                feature_name = feature.get("name", "")
                                if not feature_name:
                                    continue
                                
                                # Determine if enabled based on strategies and environment
                                strategies = feature.get("strategies", [])
                                environments = feature.get("environments", [])
                                
                                # Find environment-specific config
                                env_config = None
                                for env in environments:
                                    if env.get("name") == environment:
                                        env_config = env
                                        break
                                
                                is_enabled = False
                                if env_config:
                                    # Check if any strategy is enabled
                                    strategies = env_config.get("strategies", [])
                                    is_enabled = len(strategies) > 0 and any(
                                        s.get("disabled", False) is False for s in strategies
                                    )
                                
                                # Sync to local database
                                await self.repository.sync_from_unleash(
                                    name=feature_name,
                                    environment=environment,
                                    is_enabled=is_enabled,
                                    unleash_data=feature,
                                )
                                
                                synced_count += 1
                            except Exception as e:
                                logger.error(f"Error syncing feature {feature.get('name', 'unknown')}: {e}", exc_info=True)
                        
                        # Check if there are more pages
                        if len(features) < limit:
                            break
                        offset += limit
            
            logger.info(f"Synced {synced_count} flags from Unleash for environment {environment}")
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing flags from Unleash: {e}", exc_info=True)
            return 0

    async def get_evaluation_history(self, flag_name: str, limit: int) -> List[dict]:
        """Get evaluation history for a flag"""
        evaluations = await self.repository.get_evaluation_history(flag_name, limit)
        return [
            {
                "id": e.id,
                "flag_name": e.flag_name,
                "user_id": e.user_id,
                "context": e.context,
                "result": e.result,
                "variant": e.variant,
                "evaluated_value": e.evaluated_value,
                "environment": e.environment,
                "evaluated_at": str(e.evaluated_at),
                "evaluation_reason": e.evaluation_reason,
            }
            for e in evaluations
        ]

