"""
FastAPI router for feature flag endpoints - Unleash and Redis only
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.feature_flag_models import (
    BulkEvaluationRequest,
    FeatureFlagEvaluationRequest,
    FeatureFlagEvaluationResponse,
    FeatureFlagListResponse,
    FeatureFlagResponse,
)
from services.feature_flag_service import FeatureFlagService

router = APIRouter(prefix="/api/v1/feature-flags", tags=["Feature Flags"])


def get_feature_flag_service() -> FeatureFlagService:
    """Dependency injection for FeatureFlagService"""
    import main as app_main
    
    # Get OpenFeature client from app state or None
    openfeature_client = getattr(app_main.app.state, "openfeature_client", None)
    
    kafka_topic = os.getenv("FEATURE_FLAG_KAFKA_TOPIC", "feature-flag-events")
    cache_ttl = int(os.getenv("FEATURE_FLAG_CACHE_TTL", "300"))
    unleash_url = os.getenv("UNLEASH_URL")
    unleash_api_token = os.getenv("UNLEASH_API_TOKEN")
    
    return FeatureFlagService(
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
    # Default to UNLEASH_ENVIRONMENT or "development" if not provided
    environment = request.environment or os.getenv("UNLEASH_ENVIRONMENT", "development")
    
    return await service.evaluate_flag(
        flag_name=request.flag_name,
        user_id=request.user_id,
        context=request.context or {},
        default_value=request.default_value,
        environment=environment,
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
    
    # Default to UNLEASH_ENVIRONMENT or "development" if not provided
    environment = request.environment or os.getenv("UNLEASH_ENVIRONMENT", "development")
    
    value, reason = await service.evaluate_boolean_flag(
        flag_name=request.flag_name,
        user_id=request.user_id,
        context=request.context or {},
        default_value=request.default_value,
        environment=environment,
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
    # Default to UNLEASH_ENVIRONMENT or "development" if not provided
    environment = request.environment or os.getenv("UNLEASH_ENVIRONMENT", "development")
    
    results = await service.bulk_evaluate_flags(
        flag_names=request.flag_names,
        user_id=request.user_id,
        context=request.context or {},
        environment=environment,
    )
    return {"results": results}


@router.get("/{name}", response_model=FeatureFlagResponse, response_model_exclude_none=True)
async def get_feature_flag(
    name: str,
    environment: str = Query(..., description="Environment name"),
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Get feature flag by name from Unleash
    
    Retrieves flag details from Unleash API (cached in Redis).
    Only includes fields that are available from Unleash.
    """
    result = await service.get_feature_flag(name, environment)
    if not result:
        raise HTTPException(status_code=404, detail=f"Feature flag '{name}' not found in environment '{environment}'")
    return result


@router.get("/", response_model=FeatureFlagListResponse, response_model_exclude_none=True)
async def list_feature_flags(
    environment: str = Query(..., description="Environment name (required)"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    List feature flags from Unleash
    
    Returns paginated list of feature flags from Unleash (cached in Redis).
    All flags come from Unleash - no local flags.
    Only includes fields that are available from Unleash (null fields are excluded).
    """
    items, total = await service.get_feature_flags(environment, limit, offset)
    return FeatureFlagListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/sync")
async def sync_flags_from_unleash(
    environment: str = Query(..., description="Environment name"),
    service: FeatureFlagService = Depends(get_feature_flag_service),
):
    """
    Refresh feature flags cache from Unleash (admin)
    
    Invalidates Redis cache and fetches fresh data from Unleash API.
    This ensures the latest flags from Unleash are available.
    """
    synced_count = await service.sync_flags_from_unleash(environment)
    return {"synced_count": synced_count, "environment": environment}
