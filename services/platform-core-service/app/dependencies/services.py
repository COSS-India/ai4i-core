"""
Service dependency factories.

Routes use these via Depends() — never construct repos or services directly.
This is the only place where repositories are imported and wired into
business-logic services.
"""

import importlib
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.database import get_auth_db_optional, get_db
from app.core.redis import get_redis
from app.utils.prometheus_client import PrometheusClient
from app.repositories.alert_management.alert_definition_repository import (
    AlertDefinitionRepository,
)
from app.repositories.alert_management.alert_history_repository import (
    AlertHistoryRepository,
)
from app.repositories.alert_management.notification_receiver_repository import (
    NotificationReceiverRepository,
)
from app.repositories.alert_management.routing_rule_repository import RoutingRuleRepository
from app.repositories.feedback.feedback_reason_repository import FeedbackReasonRepository
from app.repositories.feedback.feedback_repository import FeedbackRepository
from app.repositories.model_management.model_repository import ModelRepository
from app.repositories.model_management.service_repository import ServiceRepository
from app.services.cache_service import CacheService
from app.services.feedback.feedback_service import FeedbackService

# services/{model,alert}-management/ are hyphenated by project convention, so plain
# `from` imports can't parse the path. Use importlib to pull the classes off the
# loaded modules.
ModelService = importlib.import_module("app.services.model-management.model_service").ModelService
ServiceService = importlib.import_module("app.services.model-management.service_service").ServiceService

_alert_pkg = importlib.import_module("app.services.alert-management")
AlertDefinitionService = _alert_pkg.AlertDefinitionService
NotificationReceiverService = _alert_pkg.NotificationReceiverService
RoutingRuleService = _alert_pkg.RoutingRuleService
AlertHistoryService = _alert_pkg.AlertHistoryService
SyncService = _alert_pkg.SyncService

# Single shared SyncService — its asyncio.Lock + in-progress flag must be shared
# between the periodic background loop (started in lifespan) and the per-request
# triggers fired after alert CRUD writes.
_sync_service_singleton = SyncService()


def get_prometheus_client(request: Request) -> PrometheusClient:
    """Return a configured PrometheusClient backed by the shared connection pool."""
    if not settings.prometheus_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prometheus is not configured (PROMETHEUS_URL is unset).",
        )
    return PrometheusClient(
        settings.prometheus_url,
        request.app.state.http_client,
        timeout=settings.prometheus_timeout,
    )


def get_metering_service(
    client: PrometheusClient = Depends(get_prometheus_client),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
) -> "MeteringService":
    from app.services.metering_service import MeteringService
    return MeteringService(client, auth_db)


def get_sync_service() -> "SyncService":
    """Return the process-wide SyncService singleton."""
    return _sync_service_singleton


def get_cache_service(
    redis_client: aioredis.Redis = Depends(get_redis),
) -> CacheService:
    return CacheService(
        redis_client=redis_client,
        model_ttl_seconds=settings.model_cache_ttl_seconds,
        service_ttl_seconds=settings.service_cache_ttl_seconds,
    )


def get_model_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> ModelService:
    return ModelService(
        model_repo=ModelRepository(db),
        service_repo=ServiceRepository(db),
        cache=cache,
    )


def get_service_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> ServiceService:
    return ServiceService(
        service_repo=ServiceRepository(db),
        model_repo=ModelRepository(db),
        cache=cache,
    )


def get_feedback_service(
    db: AsyncSession = Depends(get_db),
) -> FeedbackService:
    return FeedbackService(
        feedback_repo=FeedbackRepository(db),
        reason_repo=FeedbackReasonRepository(db),
    )


# ── Alert-management service factories ──


def get_definition_service(
    db: AsyncSession = Depends(get_db),
) -> "AlertDefinitionService":
    return AlertDefinitionService(repo=AlertDefinitionRepository(db))


def get_receiver_service(
    db: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
) -> "NotificationReceiverService":
    return NotificationReceiverService(
        receiver_repo=NotificationReceiverRepository(db),
        routing_rule_repo=RoutingRuleRepository(db),
        auth_db=auth_db,
    )


def get_routing_rule_service(
    db: AsyncSession = Depends(get_db),
) -> "RoutingRuleService":
    return RoutingRuleService(repo=RoutingRuleRepository(db))


def get_history_service(
    db: AsyncSession = Depends(get_db),
) -> "AlertHistoryService":
    return AlertHistoryService(repo=AlertHistoryRepository(db))
