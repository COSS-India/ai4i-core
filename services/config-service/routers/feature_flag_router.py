"""
FastAPI router for feature flag endpoints
"""
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.feature_flag_models import (
    BulkEvaluationRequest,
    FeatureFlagCreate,
    FeatureFlagEvaluationRequest,
    FeatureFlagEvaluationResponse,
    FeatureFlagListResponse,
    FeatureFlagResponse,
)
from repositories.feature_flag_repository import FeatureFlagRepository
from services.feature_flag_service import FeatureFlagService

router = APIRouter(prefix="/api/v1/feature-flags", tags=["Feature Flags"])


def get_feature_flag_service() -> FeatureFlagService:
    """Dependency injection for FeatureFlagService"""
    import main as app_main
    
    repo = FeatureFlagRepository(app_main.db_session)
    
    # Get OpenFeature client from app state or None
    openfeature_client = getattr(app_main.app.state, "openfeature_client", None)
    
    kafka_topic = os.getenv("FEATURE_FLAG_KAFKA_TOPIC", "feature-flag-events")
    cache_ttl = int(os.getenv("FEATURE_FLAG_CACHE_TTL", "300"))
    unleash_url = os.getenv("UNLEASH_URL")
    unleash_api_token = os.getenv("UNLEASH_API_TOKEN")
    
    return FeatureFlagService(
        repository=repo,
        redis_client=app_main.redis_client,
        kafka_producer=app_main.kafka_producer,
        openfeature_client=openfeature_client,
        kafka_topic=kafka_topic,
        cache_ttl=cache_ttl,
        unleash_url=unleash_url,
        unleash_api_token=unleash_api_token,
    )


@router.post("/evaluate", response_model=FeatureFlagEvaluationResponse)
async def evaluate_flag(
    request: FeatureFlagEvaluationRequest,
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Evaluate a single feature flag
    
    Supports boolean, string, integer, float, and object (dict) flag types.
    Returns detailed evaluation result including value, variant, and reason.
    """
    return await service.evaluate_flag(
        flag_name=request.flag_name,
        user_id=request.user_id,
        context=request.context or {},
        default_value=request.default_value,
        environment=request.environment,
    )


@router.post("/evaluate/boolean")
async def evaluate_boolean_flag(
    request: FeatureFlagEvaluationRequest,
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Evaluate a boolean feature flag
    
    Returns a simple boolean value indicating if the flag is enabled for the given context.
    """
    if not isinstance(request.default_value, bool):
        raise HTTPException(status_code=400, detail="default_value must be a boolean for boolean evaluation")
    
    value, reason = await service.evaluate_boolean_flag(
        flag_name=request.flag_name,
        user_id=request.user_id,
        context=request.context or {},
        default_value=request.default_value,
        environment=request.environment,
    )
    
    return {
        "flag_name": request.flag_name,
        "value": value,
        "reason": reason,
    }


@router.post("/evaluate/bulk")
async def bulk_evaluate_flags(
    request: BulkEvaluationRequest,
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Bulk evaluate multiple feature flags
    
    Evaluates all specified flags in parallel and returns results as a dictionary.
    """
    results = await service.bulk_evaluate_flags(
        flag_names=request.flag_names,
        user_id=request.user_id,
        context=request.context or {},
        environment=request.environment,
    )
    return {"results": results}


@router.post("/", response_model=FeatureFlagResponse, status_code=201)
async def create_feature_flag(
    request: FeatureFlagCreate,
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Create a new feature flag (admin)
    
    Creates a feature flag in the local database. Note that flags should typically
    be created in Unleash UI, and this endpoint is for local flag management.
    """
    return await service.create_feature_flag(request)


@router.get("/{name}", response_model=FeatureFlagResponse)
async def get_feature_flag(
    name: str,
    environment: str = Query(..., description="Environment name"),
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Get feature flag by name
    
    Retrieves flag details including status, rollout percentage, and evaluation statistics.
    """
    result = await service.get_feature_flag(name, environment)
    if not result:
        raise HTTPException(status_code=404, detail=f"Feature flag '{name}' not found in environment '{environment}'")
    return result


@router.get("/", response_model=FeatureFlagListResponse)
async def list_feature_flags(
    environment: Optional[str] = Query(None, description="Filter by environment"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    List feature flags
    
    Returns paginated list of feature flags with optional environment filter.
    """
    items, total = await service.get_feature_flags(environment, limit, offset)
    return FeatureFlagListResponse(items=items, total=total, limit=limit, offset=offset)


@router.put("/{name}", response_model=FeatureFlagResponse)
async def update_feature_flag(
    name: str,
    environment: str = Query(..., description="Environment name"),
    request: Dict = None,
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Update feature flag (admin)
    
    Updates flag properties. Only provided fields will be updated.
    """
    if not request:
        raise HTTPException(status_code=400, detail="Request body required")
    
    result = await service.update_feature_flag(name, environment, **request)
    if not result:
        raise HTTPException(status_code=404, detail=f"Feature flag '{name}' not found in environment '{environment}'")
    return result


@router.delete("/{name}", status_code=204)
async def delete_feature_flag(
    name: str,
    environment: str = Query(..., description="Environment name"),
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Delete feature flag (admin)
    
    Permanently deletes a feature flag from the local database.
    """
    ok = await service.delete_feature_flag(name, environment)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Feature flag '{name}' not found in environment '{environment}'")
    return None


@router.get("/{name}/history")
async def get_evaluation_history(
    name: str,
    environment: str = Query(..., description="Environment name"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Get evaluation history for a feature flag
    
    Returns audit trail of flag evaluations including user context and results.
    """
    # Verify flag exists
    flag = await service.get_feature_flag(name, environment)
    if not flag:
        raise HTTPException(status_code=404, detail=f"Feature flag '{name}' not found in environment '{environment}'")
    
    history = await service.get_evaluation_history(name, limit)
    return history


@router.post("/sync")
async def sync_flags_from_unleash(
    environment: str = Query(..., description="Environment name"),
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Sync flags from Unleash (admin)
    
    Fetches all flags from Unleash API and syncs them to the local database.
    """
    synced_count = await service.sync_flags_from_unleash(environment)
    return {"synced_count": synced_count, "environment": environment}

