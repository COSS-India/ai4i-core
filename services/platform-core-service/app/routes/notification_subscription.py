"""Institution Admin's Metering Notifications & Alerts subscriptions —
GET (view), PATCH (subscribe/unsubscribe) and PUT (recipients) on
tenant_notification_subscription. Deliberately separate from
app.routes.notification/app.routes.alert_catalog, which are the Adopter
Admin-only catalog surface (scope/channels/thresholds); this module never
touches configs_notification_alert beyond reading it.

An Institution Admin is scoped to their own tenant (X-Tenant-Id); an
Adopter Admin may act on any tenant — both via
app.core.permissions.authorize_own_tenant_or_admin, the same tenant
boundary the usage/application-usage dashboards already enforce.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_auth_db_optional, get_db
from app.core.permissions import authorize_own_tenant_or_admin
from app.schemas.common import MessageMeta, error_responses
from app.schemas.enums.notification_management import NotificationType
from app.schemas.notification_management.subscription import (
    ListSubscriptionResponse,
    SubscriptionListData,
    SubscriptionPatch,
    SubscriptionRecipientsUpdate,
    UpdateSubscriptionResponse,
)
from app.services.notification_management import subscription_service

router = APIRouter(
    prefix="/notification-alerts",
    tags=["Notifications & Alerts"],
)


@router.get("/subscriptions", response_model=ListSubscriptionResponse)
async def list_subscriptions(
    request: Request,
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    catalog_type: Optional[NotificationType] = Query(None, alias="type"),
    session: AsyncSession = Depends(get_db),
) -> ListSubscriptionResponse:
    """Every catalog row (optionally filtered by ``?type=``), decorated
    with this institution's effective subscription state, lock state and
    recipients."""
    authorize_own_tenant_or_admin(request, tenant_id)
    items = await subscription_service.list_subscriptions(
        session, tenant_id=tenant_id, catalog_type=catalog_type
    )
    return ListSubscriptionResponse(success=True, data=SubscriptionListData(items=items))


@router.patch("/subscriptions/{notification_id}", responses=error_responses(404, 409))
async def update_subscription_state(
    notification_id: int,
    payload: SubscriptionPatch,
    request: Request,
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    session: AsyncSession = Depends(get_db),
) -> UpdateSubscriptionResponse:
    """Subscribe or unsubscribe this institution from one INSTITUTION-scope
    catalog row. 409 if the row is currently GLOBAL-scope — there is no
    unsubscribe option to change."""
    authorize_own_tenant_or_admin(request, tenant_id)
    updated_by = request.headers.get("X-User-Id")
    item = await subscription_service.update_subscription_state(
        session,
        tenant_id=tenant_id,
        notification_id=notification_id,
        subscribed=payload.subscribed,
        updated_by=updated_by,
    )
    verb = "Subscribed to" if item.subscribed else "Unsubscribed from"
    return UpdateSubscriptionResponse(
        success=True, data=item, meta=MessageMeta(message=f"{verb} '{item.name}'.")
    )


@router.put("/subscriptions/{notification_id}", responses=error_responses(404))
async def update_subscription_recipients(
    notification_id: int,
    payload: SubscriptionRecipientsUpdate,
    request: Request,
    tenant_id: str = Query(..., description="Institution (tenant) ID."),
    session: AsyncSession = Depends(get_db),
    auth_db: Optional[AsyncSession] = Depends(get_auth_db_optional),
) -> UpdateSubscriptionResponse:
    """Replace this institution's additional recipients wholesale. Each id
    must belong to an active user of this same institution."""
    authorize_own_tenant_or_admin(request, tenant_id)
    updated_by = request.headers.get("X-User-Id")
    item = await subscription_service.update_subscription_recipients(
        session,
        tenant_id=tenant_id,
        notification_id=notification_id,
        recipients=payload.recipients,
        updated_by=updated_by,
        auth_db=auth_db,
    )
    return UpdateSubscriptionResponse(
        success=True, data=item, meta=MessageMeta(message=f"Recipients updated for '{item.name}'.")
    )
