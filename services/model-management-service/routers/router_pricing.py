"""Pricing summary for service configuration / admin UI."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db_connection import get_auth_db_session
from db_operations import fetch_pricing_summary
from logger import logger
from middleware.auth_provider import AuthProvider
from models.pricing_summary import PricingSummaryRow

router_pricing = APIRouter(tags=["Model Management", "Pricing"])


@router_pricing.get(
    "/pricing-summary",
    response_model=list[PricingSummaryRow],
    dependencies=[Depends(AuthProvider)],
    summary="Tier pricing grouped by model task type",
)
async def get_pricing_summary(
    _db: AsyncSession = Depends(get_auth_db_session),
):
    """
    Join `services` with `models` on (model_id, model_version). Groups by model `task.type`,
    returns representative Tier-1 and Tier-2 rows (prefers published, then most recently updated).
    """
    try:
        rows = await fetch_pricing_summary()
        return [PricingSummaryRow.model_validate(r) for r in rows]
    except Exception as e:
        logger.exception("get_pricing_summary failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load pricing summary",
        ) from e
