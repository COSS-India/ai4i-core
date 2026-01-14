from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from db_connection import get_tenant_db_session , get_auth_db_session
from models.tenant_email import TenantResendEmailVerificationRequest, TenantResendEmailVerificationResponse
from services.tenant_service import verify_email_token, resend_verification_email

from logger import logger
from middleware.auth_provider import AuthProvider


router = APIRouter(
    prefix="/email", 
    tags=["Email Verification"],
    dependencies=[Depends(AuthProvider)]
)


@router.get("/verify", status_code=status.HTTP_200_OK)
async def verify_email(
    background_tasks: BackgroundTasks,
    token: str = Query(..., description="Email verification token"),
    db_tenant: AsyncSession = Depends(get_tenant_db_session),
    db_auth: AsyncSession = Depends(get_auth_db_session),
):
    try:
        await verify_email_token(token, db_tenant, db_auth, background_tasks)
        logger.info(f"Email verified successfully")
        return {"message": "Email verified successfully"}
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Value error during email verification: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        logger.exception(f"Error verifying email: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

@router.post("/resend", response_model=TenantResendEmailVerificationResponse, status_code=status.HTTP_201_CREATED)
async def resend_verification(
    payload: TenantResendEmailVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        response = await resend_verification_email(payload.tenant_id, db, background_tasks)
        logger.info(f"Verification email resent successfully for Tenant ID: {payload.tenant_id}")
        return response
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Value error during email resend: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        logger.exception(f"Error resending verification email: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")