from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError , NoResultFound

from db_connection import get_tenant_db_session
from models.tenant_create import TenantRegisterRequest, TenantRegisterResponse
from models.tenant_email import TenantResendEmailVerificationRequest, TenantResendEmailVerificationResponse
from tenant_service import create_new_tenant , verify_email_token , resend_verification_email

from logger import logger


router = APIRouter(prefix="/tenant", tags=["Tenants registeration"])


@router.post("/register", response_model=TenantRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant(
    payload: TenantRegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        response = await create_new_tenant(payload, db, background_tasks)

        logger.info(f"Tenant registered successfully. Tenant Domain: {payload.domain}, Email: {payload.contact_email}")

        return response

    except HTTPException:
        raise
    except IntegrityError as ie:
        logger.error(f"Integrity error during tenant registration: {ie}")
        raise HTTPException(status_code=400, detail="Tenant with given domain or name already exists")
    except ValueError as ve:
        logger.error(f"Value error during tenant registration: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception(f"Error registering tenant: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/verify/email")
async def verify_email(
    background_tasks: BackgroundTasks,
    token: str = Query(...),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        await verify_email_token(token, db, background_tasks)
        return {"message": "Email verified successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        logger.exception(f"Error verifying email: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

@router.post("/resend/verify/email", response_model=TenantResendEmailVerificationResponse)
async def resend_verification(
    payload: TenantResendEmailVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        response = await resend_verification_email(payload.tenant_id, db, background_tasks)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        logger.exception(f"Error verifying email: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
