"""Alert-management API endpoints — all four resources in one module.

Consolidates the four source routers (definitions, receivers, routing-rules,
history) into a single file. Each resource keeps its own ``APIRouter`` for
prefix/tags clarity; they're aggregated into the module-level ``router`` that
``app/routes/__init__.py`` mounts under ``/api/v1``.

Differences from the source routers:
  - ``organization`` query params + admin-branching removed.
  - Responses wrapped in ``success_response``.
  - After every write, a config sync is scheduled as a FastAPI background task
    (``sync_configuration(blocking=False)``) so the HTTP response isn't held up.
  - ``POST /alerts/history/webhook`` stays auth-free (Alertmanager calls it);
    the gateway must carve out an auth-skip for that one path.
  - No in-service auth/actor capture: authorization is enforced upstream at the
    gateway (auth-service ``/validate``), and create/update attribution was
    dropped.
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query

from app.core.responses import success_response
from app.dependencies.services import (
    AlertDefinitionService,
    AlertHistoryService,
    NotificationReceiverService,
    RoutingRuleService,
    SyncService,
    get_definition_service,
    get_history_service,
    get_receiver_service,
    get_routing_rule_service,
    get_sync_service,
)
from app.schemas.alert_management.alert_definition import (
    AlertDefinitionCreate,
    AlertDefinitionUpdate,
)
from app.schemas.alert_management.receiver import (
    NotificationReceiverCreate,
    NotificationReceiverUpdate,
)
from app.schemas.alert_management.routing_rule import (
    RoutingRuleCreate,
    RoutingRuleTimingUpdate,
    RoutingRuleUpdate,
)

logger = logging.getLogger(__name__)


def _schedule_sync(background: BackgroundTasks, sync_svc: SyncService) -> None:
    """Fire a non-blocking config sync after a successful write."""
    background.add_task(sync_svc.sync_configuration, blocking=False)


# ── Alert definitions ────────────────────────────────────────────────────────

definitions_router = APIRouter(prefix="/alerts/definitions", tags=["Alerts - Definitions"])


@definitions_router.post("", status_code=201)
async def create_alert_definition(
    payload: AlertDefinitionCreate,
    background: BackgroundTasks,
    svc: AlertDefinitionService = Depends(get_definition_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    result = await svc.create(payload)
    _schedule_sync(background, sync_svc)
    return success_response(
        data=result, meta={"message": f"Alert definition '{payload.name}' created."}
    )


@definitions_router.get("")
async def list_alert_definitions(
    enabled_only: bool = Query(False, description="Only return enabled alerts"),
    svc: AlertDefinitionService = Depends(get_definition_service),
):
    items = await svc.list(enabled_only=enabled_only)
    return success_response(data=items, meta={"total": len(items)})


@definitions_router.get("/{alert_id}")
async def get_alert_definition(
    alert_id: int,
    svc: AlertDefinitionService = Depends(get_definition_service),
):
    return success_response(data=await svc.get(alert_id))


@definitions_router.put("/{alert_id}")
async def update_alert_definition(
    alert_id: int,
    payload: AlertDefinitionUpdate,
    background: BackgroundTasks,
    svc: AlertDefinitionService = Depends(get_definition_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    result = await svc.update(alert_id, payload)
    _schedule_sync(background, sync_svc)
    return success_response(data=result, meta={"message": "Alert definition updated."})


@definitions_router.delete("/{alert_id}")
async def delete_alert_definition(
    alert_id: int,
    background: BackgroundTasks,
    svc: AlertDefinitionService = Depends(get_definition_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    await svc.delete(alert_id)
    _schedule_sync(background, sync_svc)
    return success_response(
        data={"id": alert_id}, meta={"message": "Alert definition deleted."}
    )


@definitions_router.patch("/{alert_id}/enabled")
async def toggle_alert_definition(
    alert_id: int,
    background: BackgroundTasks,
    enabled: bool = Body(..., embed=True, description="Enable or disable the alert"),
    svc: AlertDefinitionService = Depends(get_definition_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    result = await svc.set_enabled(alert_id, enabled)
    _schedule_sync(background, sync_svc)
    return success_response(
        data=result, meta={"message": f"Alert definition {'enabled' if enabled else 'disabled'}."}
    )


# ── Notification receivers ───────────────────────────────────────────────────

receivers_router = APIRouter(prefix="/alerts/receivers", tags=["Alerts - Receivers"])


@receivers_router.post("", status_code=201)
async def create_receiver(
    payload: NotificationReceiverCreate,
    background: BackgroundTasks,
    svc: NotificationReceiverService = Depends(get_receiver_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    result = await svc.create(payload)
    _schedule_sync(background, sync_svc)
    return success_response(data=result, meta={"message": "Notification receiver created."})


@receivers_router.get("")
async def list_receivers(
    svc: NotificationReceiverService = Depends(get_receiver_service),
):
    items = await svc.list()
    return success_response(data=items, meta={"total": len(items)})


@receivers_router.get("/{receiver_id}")
async def get_receiver(
    receiver_id: int,
    svc: NotificationReceiverService = Depends(get_receiver_service),
):
    return success_response(data=await svc.get(receiver_id))


@receivers_router.put("/{receiver_id}")
async def update_receiver(
    receiver_id: int,
    payload: NotificationReceiverUpdate,
    background: BackgroundTasks,
    svc: NotificationReceiverService = Depends(get_receiver_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    result = await svc.update(receiver_id, payload)
    _schedule_sync(background, sync_svc)
    return success_response(data=result, meta={"message": "Notification receiver updated."})


@receivers_router.delete("/{receiver_id}")
async def delete_receiver(
    receiver_id: int,
    background: BackgroundTasks,
    svc: NotificationReceiverService = Depends(get_receiver_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    await svc.delete(receiver_id)
    _schedule_sync(background, sync_svc)
    return success_response(
        data={"id": receiver_id}, meta={"message": "Notification receiver deleted."}
    )


# ── Routing rules ────────────────────────────────────────────────────────────

routing_rules_router = APIRouter(prefix="/alerts/routing-rules", tags=["Alerts - Routing Rules"])


@routing_rules_router.post("", status_code=201)
async def create_routing_rule(
    payload: RoutingRuleCreate,
    background: BackgroundTasks,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    result = await svc.create(payload)
    _schedule_sync(background, sync_svc)
    return success_response(data=result, meta={"message": "Routing rule created."})


@routing_rules_router.get("")
async def list_routing_rules(
    svc: RoutingRuleService = Depends(get_routing_rule_service),
):
    items = await svc.list()
    return success_response(data=items, meta={"total": len(items)})


# NOTE: /timing must be declared before /{rule_id} so it isn't captured by the int path param.
@routing_rules_router.patch("/timing")
async def update_routing_rule_timing(
    payload: RoutingRuleTimingUpdate,
    background: BackgroundTasks,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    affected = await svc.update_timing(payload)
    _schedule_sync(background, sync_svc)
    return success_response(
        data={"affected": affected},
        meta={"message": f"Updated timing on {affected} routing rule(s)."},
    )


@routing_rules_router.get("/{rule_id}")
async def get_routing_rule(
    rule_id: int,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
):
    return success_response(data=await svc.get(rule_id))


@routing_rules_router.put("/{rule_id}")
async def update_routing_rule(
    rule_id: int,
    payload: RoutingRuleUpdate,
    background: BackgroundTasks,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    result = await svc.update(rule_id, payload)
    _schedule_sync(background, sync_svc)
    return success_response(data=result, meta={"message": "Routing rule updated."})


@routing_rules_router.delete("/{rule_id}")
async def delete_routing_rule(
    rule_id: int,
    background: BackgroundTasks,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
    sync_svc: SyncService = Depends(get_sync_service),
):
    await svc.delete(rule_id)
    _schedule_sync(background, sync_svc)
    return success_response(data={"id": rule_id}, meta={"message": "Routing rule deleted."})


# ── Alert history ────────────────────────────────────────────────────────────

history_router = APIRouter(prefix="/alerts/history", tags=["Alerts - History"])


@history_router.post("/webhook")
async def alert_history_webhook(
    payload: dict,
    svc: AlertHistoryService = Depends(get_history_service),
):
    """Alertmanager v4 webhook — AUTH-FREE (gateway must allow this path unauthenticated)."""
    recorded = await svc.record_from_webhook(payload)
    return {"status": "ok", "recorded": recorded}


@history_router.get("")
async def list_alert_history(
    category: Optional[str] = Query(None, description="Filter: application | infrastructure"),
    severity: Optional[str] = Query(None, description="Filter: critical | warning | info"),
    date_from: Optional[str] = Query(None, description="triggered_at >= (ISO 8601 or YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="triggered_at <= (ISO 8601 or YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search alert name + notified audience"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    svc: AlertHistoryService = Depends(get_history_service),
):
    items, total = await svc.list(
        category=category,
        severity=severity,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
    )
    return success_response(data=items, meta={"total": total, "limit": limit, "offset": offset})


# ── Aggregate ────────────────────────────────────────────────────────────────

router = APIRouter()
router.include_router(definitions_router)
router.include_router(receivers_router)
router.include_router(routing_rules_router)
router.include_router(history_router)
