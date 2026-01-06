from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db_connection import get_tenant_db_session
from models.tenant_subscription import (
    TenantSubscriptionAddRequest,
    TenantSubscriptionRemoveRequest,
    TenantSubscriptionResponse,
)
from tenant_service import add_subscriptions, remove_subscriptions
from logger import logger
from middleware.auth_provider import AuthProvider


router = APIRouter(
    prefix="/tenant",
    tags=["Tenant Subscriptions"],
    dependencies=[Depends(AuthProvider)],
)


@router.post("/subscriptions/add",response_model=TenantSubscriptionResponse,status_code=status.HTTP_201_CREATED)
async def add_tenant_subscriptions(
    payload: TenantSubscriptionAddRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        response = await add_subscriptions(payload.tenant_id,payload.subscriptions,db)

        logger.info(f"Subscriptions added successfully | tenant_id={payload.tenant_id} | "f"added={payload.subscriptions}")

        return response

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


@router.post("/subscriptions/remove",response_model=TenantSubscriptionResponse,status_code=status.HTTP_200_OK)
async def remove_tenant_subscriptions(
    payload: TenantSubscriptionRemoveRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        response = await remove_subscriptions(payload.tenant_id,payload.subscriptions,db)

        logger.info(f"Subscriptions removed successfully | tenant_id={payload.tenant_id} | removed={payload.subscriptions}")

        return response

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
