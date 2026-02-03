from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db_connection import get_tenant_db_session
from models.user_subscription import (
    UserSubscriptionAddRequest,
    UserSubscriptionRemoveRequest,
    UserSubscriptionResponse,
)
from services.tenant_service import (
    add_user_subscriptions,
    remove_user_subscriptions,
)
from logger import logger
from middleware.auth_provider import AuthProvider


router = APIRouter(
    prefix="/user",
    tags=["User Subscriptions"],
    # dependencies=[Depends(AuthProvider)],
)


@router.post("/subscriptions/add",response_model=UserSubscriptionResponse,status_code=status.HTTP_201_CREATED,)
async def add_user_subscriptions_endpoint(
    payload: UserSubscriptionAddRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Add subscriptions to a tenant user.
    """
    try:
        response = await add_user_subscriptions(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            subscriptions=payload.subscriptions,
            db=db,
        )

        logger.info(
            f"User subscriptions added successfully | tenant_id={payload.tenant_id} | user_id={payload.user_id} | added={payload.subscriptions}",
        )

        return response

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error while adding user subscriptions | tenant_id={payload.tenant_id} | user_id={payload.user_id} | {ie}")
        raise HTTPException(status_code=400,detail="Integrity error while adding user subscriptions")
    except ValueError as ve:
        logger.error(f"Value error while adding user subscriptions | tenant_id={payload.tenant_id} | user_id={payload.user_id} | {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Unexpected error while adding user subscriptions | tenant_id={payload.tenant_id} | user_id={payload.user_id}")
        raise HTTPException(status_code=500,detail="Internal server error")


@router.post("/subscriptions/remove",response_model=UserSubscriptionResponse,status_code=status.HTTP_200_OK)
async def remove_user_subscriptions_endpoint(
    payload: UserSubscriptionRemoveRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Remove subscriptions from a tenant user.
    """
    try:
        response = await remove_user_subscriptions(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            subscriptions=payload.subscriptions,
            db=db,
        )

        logger.info(
            f"User subscriptions removed successfully | tenant_id={payload.tenant_id} | user_id={payload.user_id} | removed={payload.subscriptions}",
        )

        return response

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error while removing user subscriptions | tenant_id={payload.tenant_id} | user_id={payload.user_id} | {ie}")
        raise HTTPException(status_code=400,detail="Integrity error while removing user subscriptions")
    except ValueError as ve:
        logger.error(f"Value error while removing user subscriptions | tenant_id={payload.tenant_id} | user_id={payload.user_id} | {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Unexpected error while removing user subscriptions | tenant_id={payload.tenant_id} | user_id={payload.user_id}")
        raise HTTPException(status_code=500,detail="Internal server error")

