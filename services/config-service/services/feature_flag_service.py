import json
import logging
from typing import List, Optional, Tuple

from redis.asyncio import Redis

from models.feature_flag_models import (
    FeatureFlagCreate,
    FeatureFlagEvaluate,
    FeatureFlagEvaluationResponse,
    FeatureFlagResponse,
)
from repositories.feature_flag_repository import FeatureFlagRepository


logger = logging.getLogger(__name__)


class FeatureFlagService:
    def __init__(self, repository: FeatureFlagRepository, redis_client: Redis, eval_ttl: int = 300):
        self.repository = repository
        self.redis = redis_client
        self.eval_ttl = eval_ttl

    def _flag_cache_key(self, environment: str, name: str) -> str:
        return f"feature_flag:{environment}:{name}"

    def _eval_cache_key(self, environment: str, name: str, user_id: str) -> str:
        return f"flag_eval:{environment}:{name}:{user_id}"

    async def create_feature_flag(self, req: FeatureFlagCreate) -> FeatureFlagResponse:
        flag = await self.repository.create_feature_flag(
            name=req.name,
            description=req.description,
            is_enabled=req.is_enabled,
            rollout_percentage=req.rollout_percentage,
            target_users=req.target_users,
            environment=req.environment,
        )
        await self.redis.delete(self._flag_cache_key(flag.environment, flag.name))
        return FeatureFlagResponse(
            id=flag.id,
            name=flag.name,
            description=flag.description,
            is_enabled=flag.is_enabled,
            rollout_percentage=float(flag.rollout_percentage or 0),
            target_users=flag.target_users or [],
            environment=flag.environment,
            created_at=str(flag.created_at),
            updated_at=str(flag.updated_at),
        )

    async def get_feature_flag(self, name: str, environment: str) -> Optional[FeatureFlagResponse]:
        ck = self._flag_cache_key(environment, name)
        cached = await self.redis.get(ck)
        if cached:
            try:
                return FeatureFlagResponse(**json.loads(cached))
            except Exception:
                pass
        flag = await self.repository.get_feature_flag(name, environment)
        if not flag:
            return None
        resp = FeatureFlagResponse(
            id=flag.id,
            name=flag.name,
            description=flag.description,
            is_enabled=flag.is_enabled,
            rollout_percentage=float(flag.rollout_percentage or 0),
            target_users=flag.target_users or [],
            environment=flag.environment,
            created_at=str(flag.created_at),
            updated_at=str(flag.updated_at),
        )
        await self.redis.set(ck, json.dumps(resp.model_dump()), ex=self.eval_ttl)
        return resp

    async def list_feature_flags(self, environment: Optional[str], enabled: Optional[bool], limit: int, offset: int):
        flags, total = await self.repository.list_feature_flags(environment, enabled, limit, offset)
        return [
            FeatureFlagResponse(
                id=f.id,
                name=f.name,
                description=f.description,
                is_enabled=f.is_enabled,
                rollout_percentage=float(f.rollout_percentage or 0),
                target_users=f.target_users or [],
                environment=f.environment,
                created_at=str(f.created_at),
                updated_at=str(f.updated_at),
            )
            for f in flags
        ], total

    async def update_feature_flag(
        self,
        name: str,
        environment: str,
        is_enabled: Optional[bool],
        rollout_percentage: Optional[float],
        target_users: Optional[List[str]],
    ) -> Optional[FeatureFlagResponse]:
        flag = await self.repository.update_feature_flag(name, environment, is_enabled, rollout_percentage, target_users)
        if not flag:
            return None
        await self.redis.delete(self._flag_cache_key(environment, name))
        return await self.get_feature_flag(name, environment)

    async def delete_feature_flag(self, name: str, environment: str) -> bool:
        ok = await self.repository.delete_feature_flag(name, environment)
        await self.redis.delete(self._flag_cache_key(environment, name))
        return ok

    async def evaluate_feature_flag(self, name: str, environment: str, user_id: str) -> FeatureFlagEvaluationResponse:
        ck = self._eval_cache_key(environment, name, user_id)
        cached = await self.redis.get(ck)
        if cached:
            try:
                data = json.loads(cached)
                return FeatureFlagEvaluationResponse(**data)
            except Exception:
                pass
        enabled, reason = await self.repository.evaluate_feature_flag(name, environment, user_id)
        resp = FeatureFlagEvaluationResponse(enabled=enabled, reason=reason)
        await self.redis.set(ck, json.dumps(resp.model_dump()), ex=self.eval_ttl)
        return resp


