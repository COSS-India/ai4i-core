"""Alert-management API endpoints — all four resources in one module.

Consolidates the four source routers (definitions, receivers, routing-rules,
history) into a single file. Each resource keeps its own ``APIRouter`` for
prefix/tags clarity; they're aggregated into the module-level ``router`` that
``app/routes/__init__.py`` mounts under ``/api/v1``.

Differences from the source routers:
  - ``organization`` query params + admin-branching removed.
  - Responses are ``{"success": true, "data": ..., "meta": ...}`` envelopes —
    built by returning the route's own response-schema instance directly
    (its return-type annotation doubles as the documented OpenAPI response),
    rather than a bare dict plus a separate ``response_model=`` kwarg.
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
    CreateAlertDefinitionResponse,
    DeleteAlertDefinitionResponse,
    GetAlertDefinitionResponse,
    ListAlertDefinitionsResponse,
    ToggleAlertDefinitionResponse,
    UpdateAlertDefinitionResponse,
)
from app.schemas.alert_management.history import (
    AlertHistoryListMeta,
    AlertHistoryWebhookResponse,
    AlertmanagerWebhookPayload,
    ListAlertHistoryResponse,
)
from app.schemas.alert_management.receiver import (
    CreateReceiverResponse,
    DeleteReceiverResponse,
    GetReceiverResponse,
    ListReceiversResponse,
    NotificationReceiverCreate,
    NotificationReceiverUpdate,
    UpdateReceiverResponse,
)
from app.schemas.alert_management.routing_rule import (
    CreateRoutingRuleResponse,
    DeleteRoutingRuleResponse,
    GetRoutingRuleResponse,
    ListRoutingRulesResponse,
    RoutingRuleCreate,
    RoutingRuleTimingUpdate,
    RoutingRuleTimingUpdateData,
    RoutingRuleUpdate,
    UpdateRoutingRuleResponse,
    UpdateRoutingRuleTimingResponse,
)
from app.schemas.common import DeletedIdData, MessageMeta, TotalMeta, error_responses

logger = logging.getLogger(__name__)


def _schedule_sync(background: BackgroundTasks, sync_svc: SyncService) -> None:
    """Fire a non-blocking config sync after a successful write."""
    background.add_task(sync_svc.sync_configuration, blocking=False)


# ── Alert definitions ────────────────────────────────────────────────────────

definitions_router = APIRouter(prefix="/alerts/definitions", tags=["Alerts - Definitions"])


@definitions_router.post("", status_code=201, responses=error_responses(409))
async def create_alert_definition(
    payload: AlertDefinitionCreate,
    background: BackgroundTasks,
    svc: AlertDefinitionService = Depends(get_definition_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> CreateAlertDefinitionResponse:
    """Create a new alert definition."""
    result = await svc.create(payload)
    _schedule_sync(background, sync_svc)
    return CreateAlertDefinitionResponse(
        success=True,
        data=result,
        meta=MessageMeta(message=f"Alert definition '{payload.name}' created."),
    )


@definitions_router.get("")
async def list_alert_definitions(
    enabled_only: bool = Query(False, description="Only return enabled alerts"),
    svc: AlertDefinitionService = Depends(get_definition_service),
) -> ListAlertDefinitionsResponse:
    """List alert definitions, optionally filtered to enabled ones."""
    items = await svc.list(enabled_only=enabled_only)
    return ListAlertDefinitionsResponse(success=True, data=items, meta=TotalMeta(total=len(items)))


@definitions_router.get("/{alert_id}", responses=error_responses(404))
async def get_alert_definition(
    alert_id: int,
    svc: AlertDefinitionService = Depends(get_definition_service),
) -> GetAlertDefinitionResponse:
    """Get a single alert definition by id."""
    return GetAlertDefinitionResponse(success=True, data=await svc.get(alert_id))


@definitions_router.put("/{alert_id}", responses=error_responses(404))
async def update_alert_definition(
    alert_id: int,
    payload: AlertDefinitionUpdate,
    background: BackgroundTasks,
    svc: AlertDefinitionService = Depends(get_definition_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> UpdateAlertDefinitionResponse:
    """Update an alert definition."""
    result = await svc.update(alert_id, payload)
    _schedule_sync(background, sync_svc)
    return UpdateAlertDefinitionResponse(
        success=True, data=result, meta=MessageMeta(message="Alert definition updated.")
    )


@definitions_router.delete("/{alert_id}", responses=error_responses(404))
async def delete_alert_definition(
    alert_id: int,
    background: BackgroundTasks,
    svc: AlertDefinitionService = Depends(get_definition_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> DeleteAlertDefinitionResponse:
    """Delete an alert definition."""
    await svc.delete(alert_id)
    _schedule_sync(background, sync_svc)
    return DeleteAlertDefinitionResponse(
        success=True,
        data=DeletedIdData(id=alert_id),
        meta=MessageMeta(message="Alert definition deleted."),
    )


@definitions_router.patch("/{alert_id}/enabled", responses=error_responses(404))
async def toggle_alert_definition(
    alert_id: int,
    background: BackgroundTasks,
    enabled: bool = Body(..., embed=True, description="Enable or disable the alert"),
    svc: AlertDefinitionService = Depends(get_definition_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> ToggleAlertDefinitionResponse:
    """Enable or disable an alert definition."""
    result = await svc.set_enabled(alert_id, enabled)
    _schedule_sync(background, sync_svc)
    return ToggleAlertDefinitionResponse(
        success=True,
        data=result,
        meta=MessageMeta(message=f"Alert definition {'enabled' if enabled else 'disabled'}."),
    )


# ── Notification receivers ───────────────────────────────────────────────────

receivers_router = APIRouter(prefix="/alerts/receivers", tags=["Alerts - Receivers"])


@receivers_router.post("", status_code=201, responses=error_responses(404, 409))
async def create_receiver(
    payload: NotificationReceiverCreate,
    background: BackgroundTasks,
    svc: NotificationReceiverService = Depends(get_receiver_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> CreateReceiverResponse:
    """Create a notification receiver, plus its paired routing rule."""
    result = await svc.create(payload)
    _schedule_sync(background, sync_svc)
    return CreateReceiverResponse(
        success=True, data=result, meta=MessageMeta(message="Notification receiver created.")
    )


@receivers_router.get("")
async def list_receivers(
    svc: NotificationReceiverService = Depends(get_receiver_service),
) -> ListReceiversResponse:
    """List notification receivers."""
    items = await svc.list()
    return ListReceiversResponse(success=True, data=items, meta=TotalMeta(total=len(items)))


@receivers_router.get("/{receiver_id}", responses=error_responses(404))
async def get_receiver(
    receiver_id: int,
    svc: NotificationReceiverService = Depends(get_receiver_service),
) -> GetReceiverResponse:
    """Get a single notification receiver by id."""
    return GetReceiverResponse(success=True, data=await svc.get(receiver_id))


@receivers_router.put("/{receiver_id}", responses=error_responses(404))
async def update_receiver(
    receiver_id: int,
    payload: NotificationReceiverUpdate,
    background: BackgroundTasks,
    svc: NotificationReceiverService = Depends(get_receiver_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> UpdateReceiverResponse:
    """Update a notification receiver."""
    result = await svc.update(receiver_id, payload)
    _schedule_sync(background, sync_svc)
    return UpdateReceiverResponse(
        success=True, data=result, meta=MessageMeta(message="Notification receiver updated.")
    )


@receivers_router.delete("/{receiver_id}", responses=error_responses(404))
async def delete_receiver(
    receiver_id: int,
    background: BackgroundTasks,
    svc: NotificationReceiverService = Depends(get_receiver_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> DeleteReceiverResponse:
    """Delete a notification receiver."""
    await svc.delete(receiver_id)
    _schedule_sync(background, sync_svc)
    return DeleteReceiverResponse(
        success=True,
        data=DeletedIdData(id=receiver_id),
        meta=MessageMeta(message="Notification receiver deleted."),
    )


# ── Routing rules ────────────────────────────────────────────────────────────

routing_rules_router = APIRouter(prefix="/alerts/routing-rules", tags=["Alerts - Routing Rules"])


@routing_rules_router.post("", status_code=201, responses=error_responses(409))
async def create_routing_rule(
    payload: RoutingRuleCreate,
    background: BackgroundTasks,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> CreateRoutingRuleResponse:
    """Create a routing rule."""
    result = await svc.create(payload)
    _schedule_sync(background, sync_svc)
    return CreateRoutingRuleResponse(
        success=True, data=result, meta=MessageMeta(message="Routing rule created.")
    )


@routing_rules_router.get("")
async def list_routing_rules(
    svc: RoutingRuleService = Depends(get_routing_rule_service),
) -> ListRoutingRulesResponse:
    """List routing rules."""
    items = await svc.list()
    return ListRoutingRulesResponse(success=True, data=items, meta=TotalMeta(total=len(items)))


# NOTE: /timing must be declared before /{rule_id} so it isn't captured by the int path param.
@routing_rules_router.patch("/timing")
async def update_routing_rule_timing(
    payload: RoutingRuleTimingUpdate,
    background: BackgroundTasks,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> UpdateRoutingRuleTimingResponse:
    """Bulk-apply timing params to every routing rule matching the given filter."""
    affected = await svc.update_timing(payload)
    _schedule_sync(background, sync_svc)
    return UpdateRoutingRuleTimingResponse(
        success=True,
        data=RoutingRuleTimingUpdateData(affected=affected),
        meta=MessageMeta(message=f"Updated timing on {affected} routing rule(s)."),
    )


@routing_rules_router.get("/{rule_id}", responses=error_responses(404))
async def get_routing_rule(
    rule_id: int,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
) -> GetRoutingRuleResponse:
    """Get a single routing rule by id."""
    return GetRoutingRuleResponse(success=True, data=await svc.get(rule_id))


@routing_rules_router.put("/{rule_id}", responses=error_responses(404, 409))
async def update_routing_rule(
    rule_id: int,
    payload: RoutingRuleUpdate,
    background: BackgroundTasks,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> UpdateRoutingRuleResponse:
    """Update a routing rule."""
    result = await svc.update(rule_id, payload)
    _schedule_sync(background, sync_svc)
    return UpdateRoutingRuleResponse(
        success=True, data=result, meta=MessageMeta(message="Routing rule updated.")
    )


@routing_rules_router.delete("/{rule_id}", responses=error_responses(404))
async def delete_routing_rule(
    rule_id: int,
    background: BackgroundTasks,
    svc: RoutingRuleService = Depends(get_routing_rule_service),
    sync_svc: SyncService = Depends(get_sync_service),
) -> DeleteRoutingRuleResponse:
    """Delete a routing rule."""
    await svc.delete(rule_id)
    _schedule_sync(background, sync_svc)
    return DeleteRoutingRuleResponse(
        success=True, data=DeletedIdData(id=rule_id), meta=MessageMeta(message="Routing rule deleted.")
    )


# ── Alert history ────────────────────────────────────────────────────────────

history_router = APIRouter(prefix="/alerts/history", tags=["Alerts - History"])


@history_router.post("/webhook")
async def alert_history_webhook(
    payload: AlertmanagerWebhookPayload,
    svc: AlertHistoryService = Depends(get_history_service),
) -> AlertHistoryWebhookResponse:
    """Alertmanager v4 webhook — AUTH-FREE (gateway must allow this path unauthenticated).

    Unlike the rest of this module, the response isn't wrapped in the
    ``{success, data}`` envelope — Alertmanager itself is the caller, not the
    portal, so this stays a bare acknowledgement.
    """
    recorded = await svc.record_from_webhook(payload.model_dump(exclude_unset=True))
    return AlertHistoryWebhookResponse(status="ok", recorded=recorded)


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
) -> ListAlertHistoryResponse:
    """List the triggered-alert audit log, with optional filters and pagination."""
    items, total = await svc.list(
        category=category,
        severity=severity,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
    )
    return ListAlertHistoryResponse(
        success=True, data=items, meta=AlertHistoryListMeta(total=total, limit=limit, offset=offset)
    )


# ── Aggregate ────────────────────────────────────────────────────────────────

router = APIRouter()
router.include_router(definitions_router)
router.include_router(receivers_router)
router.include_router(routing_rules_router)
router.include_router(history_router)
