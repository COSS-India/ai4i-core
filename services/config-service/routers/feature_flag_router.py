from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.feature_flag_models import (
    FeatureFlagCreate,
    FeatureFlagEvaluate,
    FeatureFlagEvaluationResponse,
    FeatureFlagResponse,
    FeatureFlagUpdate,
)
from repositories.feature_flag_repository import FeatureFlagRepository
from services.feature_flag_service import FeatureFlagService


router = APIRouter(prefix="/api/v1/feature-flags", tags=["Feature Flags"])


def get_flag_service() -> FeatureFlagService:
    import main as app_main  # type: ignore
    repo = FeatureFlagRepository(app_main.db_session)
    from os import getenv
    ttl = int(getenv("FEATURE_FLAG_CACHE_TTL", "300"))
    kafka_topic = getenv("KAFKA_TOPIC_FEATURE_FLAG_UPDATES", "feature-flag-updates")
    return FeatureFlagService(
        repo,
        app_main.redis_client,
        kafka_producer=app_main.kafka_producer,
        kafka_topic=kafka_topic,
        eval_ttl=ttl,
    )


@router.post("/", response_model=FeatureFlagResponse, status_code=201)
async def create_feature_flag(data: FeatureFlagCreate, service: FeatureFlagService = Depends(get_flag_service)):
    return await service.create_feature_flag(data)


@router.get("/", response_model=List[FeatureFlagResponse])
async def list_feature_flags(
    environment: Optional[str] = None,
    enabled: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    service: FeatureFlagService = Depends(get_flag_service),
):
    items, _ = await service.list_feature_flags(environment, enabled, limit, offset)
    return items


@router.get("/{name}", response_model=FeatureFlagResponse)
async def get_feature_flag(name: str, environment: str = Query(...), service: FeatureFlagService = Depends(get_flag_service)):
    result = await service.get_feature_flag(name, environment)
    if not result:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return result


@router.put("/{name}", response_model=FeatureFlagResponse)
async def update_feature_flag(
    name: str,
    data: FeatureFlagUpdate,
    environment: str = Query(...),
    service: FeatureFlagService = Depends(get_flag_service),
):
    result = await service.update_feature_flag(
        name, environment, data.is_enabled, data.rollout_percentage, data.target_users
    )
    if not result:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return result


@router.delete("/{name}", status_code=204)
async def delete_feature_flag(name: str, environment: str = Query(...), service: FeatureFlagService = Depends(get_flag_service)):
    ok = await service.delete_feature_flag(name, environment)
    if not ok:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return


@router.post("/evaluate", response_model=FeatureFlagEvaluationResponse)
async def evaluate_flag(payload: FeatureFlagEvaluate, service: FeatureFlagService = Depends(get_flag_service)):
    return await service.evaluate_feature_flag(payload.flag_name, payload.environment, payload.user_id)


@router.post("/evaluate/batch")
async def evaluate_batch(flags: List[str], user_id: str, environment: str, service: FeatureFlagService = Depends(get_flag_service)):
    results = {}
    for name in flags:
        res = await service.evaluate_feature_flag(name, environment, user_id)
        results[name] = res.model_dump()
    return results


@router.get("/{name}/history")
async def get_feature_flag_history(
    name: str,
    environment: str = Query(...),
    limit: int = Query(50, ge=1, le=100),
    service: FeatureFlagService = Depends(get_flag_service),
):
    history = await service.get_feature_flag_history(name, environment, limit)
    return [
        {
            "id": h.id,
            "old_is_enabled": h.old_is_enabled,
            "new_is_enabled": h.new_is_enabled,
            "old_rollout_percentage": h.old_rollout_percentage,
            "new_rollout_percentage": h.new_rollout_percentage,
            "old_target_users": h.old_target_users,
            "new_target_users": h.new_target_users,
            "changed_by": h.changed_by,
            "changed_at": str(h.changed_at),
        }
        for h in history
    ]


