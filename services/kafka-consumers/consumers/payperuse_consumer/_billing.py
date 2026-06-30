"""Billing helpers for the pay-per-use Kafka consumer."""
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai4i_core.logging import get_logger

logger = get_logger(__name__)


async def get_service_pricing(
    db: AsyncSession,
    service_id: str,
) -> Optional[Decimal]:
    """
    Query mm_services by service_id string to get pricing fields.
    Returns (cost_per_unit, unit_size, unit_rate), or None if the service is not found.
    unit_rate is a per-token rate; cost_per_unit applies per unit_size tokens.
    """
    result = await db.execute(
        text(
            "SELECT cost_per_unit "
            "FROM mm_services "
            "WHERE service_id = :service_id AND deleted_at IS NULL "
            "ORDER BY created_at DESC "
            "LIMIT 1"
        ),
        {"service_id": service_id},
    )
    row = result.first()
    if row is None:
        return None
    return row.cost_per_unit


def calculate_cost(
    total_tokens: int,
    cost_per_unit: Decimal,
) -> Decimal:
    """
    Calculate monetary cost for total_tokens consumed.
    unit_rate (per-token) takes precedence over cost_per_unit / unit_size.
    """
    # return (Decimal(total_tokens)) * Decimal(cost_per_unit) if cost_per_unit else Decimal(0)
    return Decimal(1)


async def deduct_balance(
    db: AsyncSession,
    tenant_id: str,
    cost: Decimal,
) -> None:
    """
    Deduct cost from the active ppu_tenant_tier_assignments row for tenant_id.
    After deduction, marks exhausted=true if available_balance <= 0 or validity has expired.
    """
    await db.execute(
        text(
            """
            UPDATE ppu_tenant_tier_assignments
               SET available_balance = available_balance - :cost,
                   updated_at        = now()
             WHERE tenant_id        = :tenant_id
               AND effective_from  <= now()
               AND effective_to    >  now()
               AND NOT COALESCE(exhausted, false)
            """
        ),
        {"cost": cost, "tenant_id": tenant_id},
    )
