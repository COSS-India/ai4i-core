from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
from middleware.dependencies import require_tenant_admin, enforce_tenant_scope


router = APIRouter(
    prefix="/user",
    tags=["User Subscriptions"],
    dependencies=[Depends(AuthProvider)],
)


@router.post("/subscriptions/add",
             response_model=UserSubscriptionResponse,
             response_model_exclude_none=True,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_tenant_admin)]
             )
async def add_user_subscriptions_endpoint(
    request: Request,
    payload: UserSubscriptionAddRequest,
    response: Response,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Add subscriptions to a tenant user.
    TENANT ADMIN can only modify their own tenant's users.
    """
    enforce_tenant_scope(request, payload.tenant_id)
    try:
        result, created_any = await add_user_subscriptions(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            subscriptions=payload.subscriptions,
            db=db,
        )
        if created_any:
            response.status_code = status.HTTP_201_CREATED
            logger.info(
                f"User subscriptions added successfully | tenant_id={payload.tenant_id} | "
                f"user_id={payload.user_id} | added={payload.subscriptions}",
            )
        else:
            response.status_code = status.HTTP_200_OK
            logger.info(
                f"No new user subscriptions added (all duplicates or empty request) | "
                f"tenant_id={payload.tenant_id} | user_id={payload.user_id}",
            )
        return result

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


@router.post("/subscriptions/remove",
             response_model=UserSubscriptionResponse,
             response_model_exclude_none=True,
             status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_tenant_admin)]
             )
async def remove_user_subscriptions_endpoint(
    request: Request,
    payload: UserSubscriptionRemoveRequest,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Remove subscriptions from a tenant user.
    TENANT ADMIN can only modify their own tenant's users.
    """
    enforce_tenant_scope(request, payload.tenant_id)
    try:
        result, removed_any = await remove_user_subscriptions(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            subscriptions=payload.subscriptions,
            db=db,
        )
        if removed_any:
            logger.info(
                f"User subscriptions removed successfully | tenant_id={payload.tenant_id} | "
                f"user_id={payload.user_id} | removed={payload.subscriptions}",
            )
        else:
            logger.info(
                f"No user subscriptions removed (none matched or empty request) | "
                f"tenant_id={payload.tenant_id} | user_id={payload.user_id}",
            )
        return result

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

