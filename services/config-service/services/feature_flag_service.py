"""
Business logic service for feature flags - Redis and Unleash only
"""
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

import aiohttp
from aiokafka import AIOKafkaProducer
from openfeature import api as openfeature_api
from openfeature.evaluation_context import EvaluationContext
from redis.asyncio import Redis

from models.feature_flag_models import (
    BulkEvaluationRequest,
    FeatureFlagEvaluationRequest,
    FeatureFlagEvaluationResponse,
    FeatureFlagListResponse,
    FeatureFlagResponse,
)

logger = logging.getLogger(__name__)


class FeatureFlagService:
    def __init__(
        self,
        redis_client: Redis,
        kafka_producer: Optional[AIOKafkaProducer],
        openfeature_client,
        kafka_topic: str,
        cache_ttl: int = 300,
        unleash_url: Optional[str] = None,
        unleash_api_token: Optional[str] = None,
    ):
        self.redis = redis_client
        self.kafka = kafka_producer
        self.openfeature_client = openfeature_client
        self.kafka_topic = kafka_topic
        self.cache_ttl = cache_ttl
        # Evaluation cache TTL should be very short to ensure accuracy
        # OpenFeature SDK refreshes every 15s, so set cache to 5s to ensure we get fresh data
        # This means cache expires 3x before SDK refresh, ensuring accuracy
        sync_interval = int(os.getenv("UNLEASH_SYNC_INTERVAL", "30"))
        # Use 5 seconds for evaluation cache - ensures fresh data, sync will also invalidate every 30s
        self.evaluation_cache_ttl = 5
        logger.info(f"Evaluation cache TTL set to {self.evaluation_cache_ttl} seconds (sync interval: {sync_interval}s, OpenFeature refresh: 15s)")
        self.unleash_url = unleash_url
        self.unleash_api_token = unleash_api_token

    def _format_auth_header(self, token: str) -> str:
        """Format Authorization header for Unleash Admin API"""
        if not token:
            return token
        
        # If already has Bearer prefix, return as is
        if token.startswith("Bearer "):
            return token
        
        # Add Bearer prefix
        return f"Bearer {token}"
    
    def _cache_key(self, environment: str, flag_name: str, user_id: Optional[str], context: Optional[dict] = None) -> str:
        """Generate cache key for flag evaluation with context hash"""
        user_part = user_id or "anonymous"
        
        # Hash context attributes for cache key
        context_hash = None
        if context:
            try:
                # Sort keys for consistent hashing
                context_json = json.dumps(context, sort_keys=True)
                context_hash = hashlib.sha256(context_json.encode('utf-8')).hexdigest()[:16]
            except Exception as e:
                logger.warning(f"Failed to hash context for cache key: {e}")
        
        context_part = f":{context_hash}" if context_hash else ""
        return f"feature_flag:eval:{environment}:{flag_name}:{user_part}{context_part}"
    
    def _flags_cache_key(self, environment: str) -> str:
        """Cache key for list of flags"""
        return f"feature_flags:list:{environment}"
    
    def _flag_metadata_key(self, environment: str, flag_name: str) -> str:
        """Cache key for flag metadata"""
        return f"feature_flag:metadata:{environment}:{flag_name}"
    
    async def _invalidate_cache(self, environment: str, flag_name: str) -> None:
        """Invalidate cache keys matching pattern for a flag"""
        try:
            pattern = f"feature_flag:eval:{environment}:{flag_name}:*"
            cursor = 0
            deleted_count = 0
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                
                if keys:
                    deleted = await self.redis.delete(*keys)
                    deleted_count += deleted
                
                if cursor == 0:
                    break
            
            # Also invalidate flag metadata and list cache
            await self.redis.delete(self._flag_metadata_key(environment, flag_name))
            await self.redis.delete(self._flags_cache_key(environment))
            
            if deleted_count > 0:
                logger.info(f"Invalidated {deleted_count} cache keys for flag {flag_name} in {environment}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for flag {flag_name} in {environment}: {e}", exc_info=True)
    
    async def invalidate_environment_cache(self, environment: str) -> None:
        """Invalidate all cache keys for an environment (used by webhooks)"""
        try:
            # Invalidate flag list cache
            await self.redis.delete(self._flags_cache_key(environment))
            
            # Invalidate all evaluation caches for this environment
            pattern = f"feature_flag:eval:{environment}:*"
            cursor = 0
            deleted_count = 0
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                
                if keys:
                    deleted = await self.redis.delete(*keys)
                    deleted_count += deleted
                
                if cursor == 0:
                    break
            
            # Invalidate all metadata caches for this environment
            metadata_pattern = f"feature_flag:metadata:{environment}:*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=metadata_pattern, count=100)
                
                if keys:
                    await self.redis.delete(*keys)
                
                if cursor == 0:
                    break
            
            logger.info(f"Invalidated all caches for environment '{environment}' (deleted {deleted_count} evaluation cache keys)")
        except Exception as e:
            logger.error(f"Failed to invalidate environment cache for {environment}: {e}", exc_info=True)
    
    async def invalidate_flag_cache(self, flag_name: str, environment: Optional[str] = None) -> None:
        """Invalidate cache for a specific flag, optionally for a specific environment"""
        try:
            if environment:
                # Invalidate for specific environment
                await self._invalidate_cache(environment, flag_name)
            else:
                # Invalidate for all environments - scan for all environments
                pattern = f"feature_flag:*:{flag_name}*"
                cursor = 0
                deleted_count = 0
                
                while True:
                    cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                    
                    if keys:
                        deleted = await self.redis.delete(*keys)
                        deleted_count += deleted
                    
                    if cursor == 0:
                        break
                
                # Also invalidate list caches (they contain this flag)
                list_pattern = "feature_flags:list:*"
                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(cursor, match=list_pattern, count=100)
                    
                    if keys:
                        # Delete all list caches since they may contain this flag
                        await self.redis.delete(*keys)
                    
                    if cursor == 0:
                        break
                
                logger.info(f"Invalidated all caches for flag '{flag_name}' (deleted {deleted_count} keys)")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for flag {flag_name}: {e}", exc_info=True)

    async def _publish(self, payload: Dict[str, Any]) -> None:
        """Publish event to Kafka"""
        if not self.kafka:
            return
        try:
            await self.kafka.send_and_wait(self.kafka_topic, json.dumps(payload).encode("utf-8"))
        except Exception as e:
            logger.warning(f"Failed to publish Kafka event: {e}")

    def _build_evaluation_context(self, user_id: Optional[str], context: dict, environment: str) -> EvaluationContext:
        """Build OpenFeature EvaluationContext from user_id, context, and environment"""
        # Include environment in attributes so Unleash provider can use it
        attributes = (context or {}).copy()
        attributes["environment"] = environment
        return EvaluationContext(
            targeting_key=user_id,
            attributes=attributes,
        )
    
    def _evaluate_with_admin_api_data(
        self,
        flag_metadata: FeatureFlagResponse,
        user_id: Optional[str],
        context: dict,
        default_value: Any,
        environment: str,
    ) -> Tuple[Any, str]:
        """
        Evaluate flag using Admin API metadata (works for any environment)
        This implements basic targeting evaluation without requiring SDK
        """
        # Flag is enabled, check targeting
        rollout_percentage = flag_metadata.rollout_percentage
        target_users = flag_metadata.target_users
        
        # Check user targeting first
        if target_users and user_id:
            if user_id in target_users:
                return (True if isinstance(default_value, bool) else default_value), "TARGETING_MATCH"
        
        # Check percentage rollout
        if rollout_percentage:
            try:
                percentage = float(rollout_percentage)
                if percentage >= 100:
                    return (True if isinstance(default_value, bool) else default_value), "TARGETING_MATCH"
                elif percentage > 0 and user_id:
                    # Simple hash-based rollout (consistent for same user)
                    import hashlib
                    hash_value = int(hashlib.md5(f"{flag_metadata.name}:{user_id}".encode()).hexdigest(), 16)
                    user_percentage = (hash_value % 100) + 1
                    if user_percentage <= percentage:
                        return (True if isinstance(default_value, bool) else default_value), "TARGETING_MATCH"
            except (ValueError, TypeError):
                pass
        
        # No targeting matched, but flag is enabled
        # For boolean flags, return True; for others, return default
        if isinstance(default_value, bool):
            return True, "TARGETING_MATCH"
        else:
            return default_value, "DEFAULT"

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
        
        # Check cache first (with very short TTL of 5s to ensure accuracy)
        cached = await self.redis.get(cache_key)
        if cached:
            try:
                if isinstance(cached, bytes):
                    cached = cached.decode('utf-8')
                data = json.loads(cached)
                # Log cache hit for debugging
                logger.debug(f"Cache hit for flag '{flag_name}' in environment '{environment}'")
                return FeatureFlagEvaluationResponse(**data)
            except Exception as e:
                logger.debug(f"Failed to parse cached evaluation result: {e}")
                # Continue to fresh evaluation if cache parse fails

        # First, check the flag's enabled state from Unleash Admin API for the requested environment
        # This ensures we're using the correct environment's flag state (same as list endpoint)
        flag_metadata = await self.get_feature_flag(flag_name, environment)
        if not flag_metadata:
            # Flag doesn't exist in this environment, return default
            logger.debug(f"Flag '{flag_name}' not found in environment '{environment}', returning default value")
            response = FeatureFlagEvaluationResponse(
                flag_name=flag_name,
                value=default_value,
                variant=None,
                reason="ERROR",
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )
            await self.redis.set(cache_key, json.dumps(response.model_dump()), ex=self.evaluation_cache_ttl)
            return response
        
        # Check if flag is enabled in this environment
        if not flag_metadata.is_enabled:
            # Flag is disabled in this environment, return default value
            logger.debug(f"Flag '{flag_name}' is disabled in environment '{environment}', returning default value")
            response = FeatureFlagEvaluationResponse(
                flag_name=flag_name,
                value=default_value,
                variant=None,
                reason="DISABLED",
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )
            await self.redis.set(cache_key, json.dumps(response.model_dump()), ex=self.evaluation_cache_ttl)
            return response

        # Flag is enabled, proceed with evaluation
        # We'll use Admin API data first, then fall back to SDK if available and needed
        value = default_value
        reason = "ERROR"
        variant = None

        # Check if flag has targeting strategies that need evaluation
        has_targeting = (
            (flag_metadata.rollout_percentage and flag_metadata.rollout_percentage not in ["0", "100"]) or
            (flag_metadata.target_users and len(flag_metadata.target_users) > 0)
        )

        # For simple boolean flags without targeting, return enabled value directly
        if isinstance(default_value, bool) and not has_targeting:
            value = True  # Flag is enabled, no targeting, so return True
            reason = "TARGETING_MATCH"
        elif has_targeting:
            # Flag has targeting - try to evaluate using SDK if available, otherwise use Admin API data
            eval_context = self._build_evaluation_context(user_id, context, environment)
            
            # Try SDK first if available
            if self.openfeature_client:
                try:
                    # Determine type and evaluate
                    if isinstance(default_value, bool):
                        details = self.openfeature_client.get_boolean_details(flag_name, default_value, eval_context)
                        value = details.value
                        reason = details.reason
                        
                        # If SDK returned DEFAULT but flag is enabled, evaluate using Admin API data
                        if reason == "DEFAULT" and flag_metadata.is_enabled:
                            value, reason = self._evaluate_with_admin_api_data(
                                flag_metadata, user_id, context, default_value, environment
                            )
                    elif isinstance(default_value, str):
                        details = self.openfeature_client.get_string_details(flag_name, default_value, eval_context)
                        value = details.value
                        reason = details.reason
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
                        variant = getattr(details, 'variant', None)
                except AttributeError as ae:
                    if "to_flag_evaluation_details" in str(ae):
                        logger.warning(f"OpenFeature SDK compatibility issue for {flag_name}, using default value")
                        value = default_value
                        reason = "ERROR"
                    else:
                        raise
                except Exception as sdk_error:
                    logger.debug(f"SDK evaluation failed, falling back to Admin API evaluation: {sdk_error}")
                    # Fall through to Admin API evaluation
            
            # If SDK not available or failed, evaluate using Admin API data
            if value == default_value and reason == "ERROR":
                value, reason = self._evaluate_with_admin_api_data(
                    flag_metadata, user_id, context, default_value, environment
                )
        else:
            # For non-boolean flags without targeting, use SDK if available, otherwise return default
            eval_context = self._build_evaluation_context(user_id, context, environment)
            if self.openfeature_client:
                try:
                    if isinstance(default_value, str):
                        details = self.openfeature_client.get_string_details(flag_name, default_value, eval_context)
                        value = details.value
                        reason = details.reason
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
                        variant = getattr(details, 'variant', None)
                except Exception as e:
                    logger.debug(f"SDK evaluation failed for non-boolean flag: {e}")
                    value = default_value
                    reason = "ERROR"
            else:
                # No SDK, return default for non-boolean flags
                value = default_value
                reason = "ERROR"

        # Cache result with shorter TTL for evaluation to ensure accuracy
        response = FeatureFlagEvaluationResponse(
            flag_name=flag_name,
            value=value,
            variant=variant,
            reason=reason,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        await self.redis.set(cache_key, json.dumps(response.model_dump()), ex=self.evaluation_cache_ttl)

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
        # Use evaluate_flag to ensure environment-specific enabled state is checked
        response = await self.evaluate_flag(
            flag_name=flag_name,
            user_id=user_id,
            context=context,
            default_value=default_value,
            environment=environment,
        )
        # Extract boolean value and reason from response
        value = bool(response.value) if isinstance(response.value, (bool, int, str)) else default_value
        return value, response.reason

    async def evaluate_string_flag(
        self,
        flag_name: str,
        user_id: Optional[str],
        context: dict,
        default_value: str,
        environment: str,
    ) -> str:
        """Evaluate string flag and return string value"""
        eval_context = self._build_evaluation_context(user_id, context, environment)
        
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
        eval_context = self._build_evaluation_context(user_id, context, environment)
        
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
        eval_context = self._build_evaluation_context(user_id, context, environment)
        
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
        eval_context = self._build_evaluation_context(user_id, context, environment)
        
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
                    default_value=False,
                    environment=environment,
                )
                return flag_name, result.model_dump()
            except Exception as e:
                logger.error(f"Error evaluating flag {flag_name} in bulk: {e}")
                return flag_name, {"error": str(e)}

        results = await asyncio.gather(*[eval_single(name) for name in flag_names])
        return {name: result for name, result in results}

    async def get_feature_flag(self, name: str, environment: str) -> Optional[FeatureFlagResponse]:
        """Get feature flag by name from Unleash (cached in Redis)"""
        # Check Redis cache first
        metadata_key = self._flag_metadata_key(environment, name)
        cached = await self.redis.get(metadata_key)
        if cached:
            try:
                if isinstance(cached, bytes):
                    cached = cached.decode('utf-8')
                data = json.loads(cached)
                return FeatureFlagResponse(**data)
            except Exception:
                pass
        
        # Fetch from Unleash API
        if not self.unleash_url or not self.unleash_api_token:
            logger.error("Unleash URL or API token not configured")
            return None
        
        try:
            base_url = self.unleash_url.rstrip('/api')
            admin_url = f"{base_url}/api/admin/projects/default/features/{name}"
            
            headers = {
                "Authorization": self._format_auth_header(self.unleash_api_token),
                "Content-Type": "application/json",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(admin_url, headers=headers) as response:
                    if response.status == 404:
                        return None
                    if response.status == 403:
                        error_text = await response.text()
                        logger.error(f"403 Forbidden - Token type mismatch. Admin API requires an Admin token, not a Client token.")
                        logger.error(f"Error details: {error_text[:500]}")
                        logger.error(f"To fix: Create an Admin token in Unleash UI (Settings → API Access) and update UNLEASH_API_TOKEN")
                        return None
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Failed to fetch feature from Unleash: {response.status}. Response: {error_text[:500]}")
                        return None
                    
                    feature = await response.json()
                    flag_response = self._convert_unleash_feature_to_response(feature, environment)
                    
                    # Cache in Redis
                    if flag_response:
                        await self.redis.set(
                            metadata_key,
                            json.dumps(flag_response.model_dump()),
                            ex=self.cache_ttl
                        )
                    
                    return flag_response
        except Exception as e:
            logger.error(f"Error fetching feature flag {name} from Unleash: {e}", exc_info=True)
            return None

    async def get_feature_flags(
        self,
        environment: Optional[str],
        limit: int,
        offset: int,
    ) -> Tuple[List[FeatureFlagResponse], int]:
        """Get feature flags from Unleash (cached in Redis)"""
        if not environment:
            logger.error("Environment is required")
            return [], 0
        
        # Check Redis cache first
        cache_key = self._flags_cache_key(environment)
        cached = await self.redis.get(cache_key)
        if cached:
            try:
                if isinstance(cached, bytes):
                    cached = cached.decode('utf-8')
                data = json.loads(cached)
                flags = [FeatureFlagResponse(**item) for item in data.get("flags", [])]
                total = data.get("total", len(flags))
                # Apply pagination
                paginated_flags = flags[offset:offset + limit]
                return paginated_flags, total
            except Exception:
                pass
        
        # Fetch from Unleash API
        if not self.unleash_url or not self.unleash_api_token:
            logger.error("Unleash URL or API token not configured")
            return [], 0
        
        try:
            base_url = self.unleash_url.rstrip('/api')
            admin_url = f"{base_url}/api/admin/projects/default/features"
            
            logger.info(f"Fetching feature flags from Unleash: {admin_url} for environment: {environment}")
            
            headers = {
                "Authorization": self._format_auth_header(self.unleash_api_token),
                "Content-Type": "application/json",
            }
            
            all_flags = []
            page_offset = 0
            page_limit = 100
            
            async with aiohttp.ClientSession() as session:
                while True:
                    params = {"offset": page_offset, "limit": page_limit}
                    async with session.get(admin_url, headers=headers, params=params) as response:
                        if response.status == 403:
                            error_text = await response.text()
                            logger.error(f"403 Forbidden - Token type mismatch. Admin API requires an Admin token, not a Client token.")
                            logger.error(f"Error details: {error_text[:500]}")
                            logger.error(f"To fix: Create an Admin token in Unleash UI (Settings → API Access) and update UNLEASH_API_TOKEN")
                            break
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Failed to fetch features from Unleash: {response.status}. Response: {error_text[:500]}")
                            break
                        
                        data = await response.json()
                        
                        # Log response structure for debugging (first page only)
                        if page_offset == 0:
                            import json as json_lib
                            logger.info(f"Unleash API response (first 2000 chars): {json_lib.dumps(data, indent=2)[:2000]}")
                        
                        # Handle different response formats
                        if isinstance(data, list):
                            features = data
                            logger.info(f"Response is a list with {len(features)} features")
                        elif isinstance(data, dict):
                            features = data.get("features", [])
                            logger.info(f"Response is a dict with 'features' key containing {len(features)} features")
                            if "features" not in data and data:
                                logger.warning(f"Unexpected response structure. Keys: {list(data.keys())}")
                        else:
                            logger.error(f"Unexpected response type: {type(data)}")
                            features = []
                        
                        if not features:
                            if page_offset == 0:
                                logger.warning(f"No features found in Unleash API response for environment '{environment}'")
                            break
                        
                        logger.info(f"Processing {len(features)} features from page {page_offset // page_limit + 1}")
                        
                        # Convert each feature
                        converted_count = 0
                        for feature in features:
                            flag_response = self._convert_unleash_feature_to_response(feature, environment)
                            if flag_response:
                                all_flags.append(flag_response)
                                converted_count += 1
                            else:
                                logger.debug(f"Failed to convert feature: {feature.get('name', 'unknown')}")
                        
                        logger.info(f"Converted {converted_count} out of {len(features)} features for environment '{environment}'")
                        
                        if len(features) < page_limit:
                            break
                        page_offset += page_limit
            
            # Cache in Redis
            if all_flags:
                cache_data = {
                    "flags": [flag.model_dump() for flag in all_flags],
                    "total": len(all_flags),
                }
                await self.redis.set(cache_key, json.dumps(cache_data), ex=self.cache_ttl)
                logger.info(f"Cached {len(all_flags)} flags in Redis for environment '{environment}'")
            else:
                logger.warning(f"No flags were converted for environment '{environment}'. This could mean:")
                logger.warning("  1. No flags exist in Unleash")
                logger.warning("  2. Environment name mismatch (check UNLEASH_ENVIRONMENT)")
                logger.warning("  3. Flags exist but not configured for this environment")
            
            # Apply pagination
            paginated_flags = all_flags[offset:offset + limit]
            logger.info(f"Returning {len(paginated_flags)} flags (offset={offset}, limit={limit}) out of {len(all_flags)} total")
            return paginated_flags, len(all_flags)
            
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error fetching feature flags from Unleash: {e}", exc_info=True)
            return [], 0
        except Exception as e:
            logger.error(f"Error fetching feature flags from Unleash: {e}", exc_info=True)
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return [], 0

    def _convert_unleash_feature_to_response(
        self,
        feature: dict,
        environment: str,
    ) -> Optional[FeatureFlagResponse]:
        """Convert Unleash API feature to FeatureFlagResponse"""
        try:
            feature_name = feature.get("name", "")
            if not feature_name:
                logger.debug("Feature missing name field, skipping")
                return None
            
            description = feature.get("description") or ""
            environments = feature.get("environments", [])
            
            logger.debug(f"Converting feature '{feature_name}' with {len(environments)} environments")
            
            # Find environment-specific config - try exact match first, then case-insensitive
            env_config = None
            available_envs = []
            for env in environments:
                if isinstance(env, dict):
                    env_name = env.get("name", "")
                    available_envs.append(env_name)
                    if env_name == environment:
                        env_config = env
                        break
            
            # Try case-insensitive match if exact match failed
            if not env_config:
                for env in environments:
                    if isinstance(env, dict):
                        env_name = env.get("name", "")
                        if env_name.lower() == environment.lower():
                            env_config = env
                            logger.debug(f"Matched environment '{env_name}' (case-insensitive) for '{environment}'")
                            break
            
            rollout_percentage = None
            target_users = None
            
            if not env_config:
                logger.debug(f"Feature '{feature_name}' does not have environment '{environment}'. Available: {available_envs}")
                # Filter out flags that don't have the requested environment
                return None
            else:
                is_enabled = env_config.get("enabled", False)
            
            # Note: The list endpoint may not include full strategy details
            # The environment object might have hasStrategies: true but no strategies array
            if env_config:
                strategies = env_config.get("strategies", [])
                
                # If strategies array is empty but hasStrategies is true,
                # the list endpoint doesn't include full strategy details
                # We'll still return the flag but without strategy-specific data
                if not strategies and env_config.get("hasStrategies", False):
                    logger.debug(f"Feature '{feature_name}' has strategies but they're not in the list response. Strategy details unavailable.")
                
                # Extract rollout_percentage and target_users from strategies
                for strategy in strategies:
                    if strategy.get("disabled", False):
                        continue
                    
                    strategy_name = strategy.get("name", "").lower()
                    parameters = strategy.get("parameters", {})
                    
                    if "gradual" in strategy_name or "rollout" in strategy_name:
                        percentage = parameters.get("percentage") or parameters.get("rollout")
                        if percentage is not None:
                            rollout_percentage = str(percentage)
                    
                    if "user" in strategy_name and "id" in strategy_name:
                        user_ids = parameters.get("userIds")
                        if isinstance(user_ids, str):
                            target_users = [uid.strip() for uid in user_ids.split(",") if uid.strip()]
                        elif isinstance(user_ids, list):
                            target_users = [str(uid) for uid in user_ids if uid]
                    
                    constraints = strategy.get("constraints", [])
                    for constraint in constraints:
                        if constraint.get("contextName") == "userId" and constraint.get("operator") == "IN":
                            values = constraint.get("values", [])
                            if values:
                                target_users = [str(v) for v in values]
            
            # Build response with only available data from Unleash
            # Only include fields that have actual values (not null/empty)
            response_data = {
                "name": feature_name,
                "is_enabled": is_enabled,
                "environment": environment,
            }
            
            # Only include description if it exists and is not empty
            if description and description.strip():
                response_data["description"] = description.strip()
            
            # Only include rollout_percentage if we extracted it from strategies
            # Note: List endpoint may not include strategy details, so this may be None
            if rollout_percentage:
                response_data["rollout_percentage"] = rollout_percentage
            
            # Only include target_users if we extracted it from strategies
            # Note: List endpoint may not include strategy details, so this may be None
            if target_users:
                response_data["target_users"] = target_users
            
            # Include unleash_flag_name (always same as name in this architecture)
            response_data["unleash_flag_name"] = feature_name
            
            # Include sync timestamp (always available)
            response_data["last_synced_at"] = datetime.now(timezone.utc).isoformat()
            
            # Include created_at if available from Unleash
            created_at = feature.get("createdAt")
            if created_at:
                response_data["created_at"] = created_at
            
            # Include updated_at if available from Unleash
            updated_at = feature.get("updatedAt")
            if updated_at:
                response_data["updated_at"] = updated_at
            
            # Create response - None values will be excluded by model's exclude_none=True
            return FeatureFlagResponse(**response_data)
        except Exception as e:
            logger.error(f"Error converting Unleash feature to response: {e}", exc_info=True)
            return None

    async def sync_flags_from_unleash(self, environment: str) -> int:
        """Sync flags from Unleash Admin API - refreshes Redis cache"""
        logger.info(f"Refreshing feature flags cache from Unleash for environment '{environment}'")
        logger.info(f"Unleash URL: {self.unleash_url}, Token: {self.unleash_api_token[:20] if self.unleash_api_token else 'None'}...")
        
        if not self.unleash_url or not self.unleash_api_token:
            logger.error("Unleash URL or API token not configured")
            return 0
        
        # Invalidate ALL caches for this environment (list, metadata, and evaluation caches)
        # This ensures fresh data for both list and evaluate endpoints
        await self.invalidate_environment_cache(environment)
        logger.info(f"Invalidated all caches for environment '{environment}' (list, metadata, and evaluation caches)")
        
        # Fetch flags (this will populate cache)
        flags, total = await self.get_feature_flags(environment, limit=1000, offset=0)
        
        if total == 0:
            logger.warning(f"No flags found after sync. Check:")
            logger.warning(f"  1. Flags exist in Unleash UI")
            logger.warning(f"  2. Environment name matches: '{environment}'")
            logger.warning(f"  3. API token has admin access")
        else:
            logger.info(f"Successfully refreshed {total} feature flags from Unleash for environment {environment}")
        
        return total
