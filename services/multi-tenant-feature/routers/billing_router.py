from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError , NoResultFound

from db_connection import get_tenant_db_session
from models.billing_update import BillingUpdateRequest, BillingUpdateResponse

from tenant_service import create_new_tenant , update_billing_plan
from logger import logger




router = APIRouter(prefix="/billing", tags=["Tenants Billing"])


@router.post("/update/plan",response_model=BillingUpdateResponse,status_code=status.HTTP_200_OK)
async def update_billing(
    payload: BillingUpdateRequest,
    db: AsyncSession = Depends(get_tenant_db_session)
    ):
    try:
        result =  await update_billing_plan(db, payload)
    
        logger.info(f"Billing plan updated successfully for Tenant ID: {payload.tenant_id}")
    
    except NoResultFound:
        logger.error(f"Billing record not found for Tenant ID: {payload.tenant_id}")
        raise HTTPException(status_code=404, detail="Tenant billing record not found")
    except ValueError as ve:
        logger.error(f"Value error during billing plan update for Tenant ID: {payload.tenant_id}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        logger.exception(f"Error updating billing plan for Tenant ID: {payload.tenant_id}")
        raise HTTPException(status_code=500, detail="Internal server error")