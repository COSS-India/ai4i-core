from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db_connection import get_tenant_db_session, get_auth_db_session
from models.tenant_subscription import (
    TenantSubscriptionAddRequest,
    TenantSubscriptionRemoveRequest,
    TenantSubscriptionResponse,
)
from services.tenant_service import add_subscriptions, remove_subscriptions
from utils.tenant_resolver import resolve_tenant_from_user_id
from logger import logger
from middleware.auth_provider import AuthProvider
from middleware.dependencies import require_admin


router = APIRouter(
    prefix="/tenant",
    tags=["Tenant Subscriptions"],
    dependencies=[Depends(AuthProvider)],
)


tenant_resolve_router = APIRouter(
    prefix="/resolve/tenant",
    tags=["Tenant Resolution"],
    dependencies=[Depends(AuthProvider)]
)


@router.post("/subscriptions/add",
             response_model=TenantSubscriptionResponse,
             response_model_exclude_none=True,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)]
             )
async def add_tenant_subscriptions(
    payload: TenantSubscriptionAddRequest,
    response: Response,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        result, created_any = await add_subscriptions(
            payload.tenant_id, payload.subscriptions, db
        )
        if created_any:
            response.status_code = status.HTTP_201_CREATED
            logger.info(
                f"Subscriptions added successfully | tenant_id={payload.tenant_id} | "
                f"added={payload.subscriptions}"
            )
        else:
            response.status_code = status.HTTP_200_OK
            logger.info(
                f"No new tenant subscriptions added (all duplicates or empty request) | "
                f"tenant_id={payload.tenant_id}"
            )
        return result

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error while adding subscriptions | tenant_id={payload.tenant_id} | {ie}")
        raise HTTPException(status_code=400,detail="Integrity error while adding subscriptions",)
    except ValueError as ve:
        logger.error(f"Value error while adding subscriptions | tenant_id={payload.tenant_id} | {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Unexpected error while adding subscriptions | tenant_id={payload.tenant_id}")
        raise HTTPException(status_code=500,detail="Internal server error")


@router.post("/subscriptions/remove",
             response_model=TenantSubscriptionResponse,
             response_model_exclude_none=True,
             status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_admin)]
             )
async def remove_tenant_subscriptions(
    payload: TenantSubscriptionRemoveRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        result, removed_any = await remove_subscriptions(
            payload.tenant_id, payload.subscriptions, db
        )
        if removed_any:
            logger.info(
                f"Subscriptions removed successfully | tenant_id={payload.tenant_id} | "
                f"removed={payload.subscriptions}"
            )
        else:
            logger.info(
                f"No tenant subscriptions removed (none matched or empty request) | "
                f"tenant_id={payload.tenant_id}"
            )
        return result

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error while removing subscriptions | tenant_id={payload.tenant_id} | {ie}")
        raise HTTPException(status_code=400,detail="Integrity error while removing subscriptions",)
    except ValueError as ve:
        logger.error(f"Value error while removing subscriptions | tenant_id={payload.tenant_id} | {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Unexpected error while removing subscriptions | tenant_id={payload.tenant_id}")
        raise HTTPException(status_code=500,detail="Internal server error",)


# Separate router for tenant resolution (no auth required for internal service calls)
@tenant_resolve_router.get("/from/user", status_code=status.HTTP_200_OK)
async def resolve_tenant_from_user(
    user_id: int,
    tenant_db: AsyncSession = Depends(get_tenant_db_session),
    auth_db: AsyncSession = Depends(get_auth_db_session),
):
    """
    Resolve tenant context from user_id.
    Used by services to get tenant schema information for routing.
    """
    try:
        tenant_context = await resolve_tenant_from_user_id(
            user_id=user_id,
            tenant_db=tenant_db,
            auth_db=auth_db
        )
        
        if not tenant_context:
            raise HTTPException(
                status_code=404,
                detail=f"Tenant not found for user_id {user_id}"
            )
        
        logger.info(f"Tenant resolved for user_id {user_id}: tenant_id={tenant_context.get('tenant_id')}")
        return tenant_context
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error resolving tenant for user_id {user_id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while resolving tenant"
        )
