"""Billing helpers for the pay-per-use Kafka consumer."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai4i_core.bootstrap import get_redis_client
from ai4i_core.logging import get_logger

logger = get_logger(__name__)

_PRICING_CACHE_PREFIX = "ppu:svc:"
_PRICING_CACHE_TTL = 3600  # 1 hour


@dataclass
class ServicePricing:
    billing_unit_type: str   # "llm", "asr", "nmt" — maps to inference_name
    unit_rate: Optional[Decimal]       # ₹ per single raw unit (preferred)
    cost_per_unit: Optional[Decimal]   # ₹ per unit_size units (fallback)
    unit_size: Optional[int]           # scaling divisor


@dataclass
class WalletResult:
    available_balance: Decimal
    tier_id: Optional[str]
    exhausted: bool  # balance <= 0 or no active assignment


async def get_service_pricing(
    db: AsyncSession,
    service_id: str,
) -> Optional[ServicePricing]:
    """Return pricing for service_id; checks Redis cache before hitting DB."""
    try:
        redis = get_redis_client()
    except RuntimeError:
        redis = None
    cache_key = f"{_PRICING_CACHE_PREFIX}{service_id}"

    if redis is not None:
        cached = await redis.hgetall(cache_key)
        if cached:
            return ServicePricing(
                billing_unit_type=cached.get("billing_unit_type", ""),
                unit_rate=Decimal(cached["unit_rate"]) if cached.get("unit_rate") else None,
                cost_per_unit=Decimal(cached["cost_per_unit"]) if cached.get("cost_per_unit") else None,
                unit_size=int(cached["unit_size"]) if cached.get("unit_size") else None,
            )

    result = await db.execute(
        text(
            "SELECT billing_unit_type, unit_rate, cost_per_unit, unit_size"
            " FROM mm_services"
            " WHERE service_id = :service_id AND deleted_at IS NULL"
            " ORDER BY created_at DESC"
            " LIMIT 1"
        ),
        {"service_id": service_id},
    )
    row = result.first()
    if row is None:
        return None

    pricing = ServicePricing(
        billing_unit_type=row.billing_unit_type or "",
        unit_rate=Decimal(str(row.unit_rate)) if row.unit_rate is not None else None,
        cost_per_unit=Decimal(str(row.cost_per_unit)) if row.cost_per_unit is not None else None,
        unit_size=int(row.unit_size) if row.unit_size else None,
    )

    # Only cache when the service has a billing_unit_type configured; otherwise
    # a stale empty entry would block billing for 1 hour after admin adds pricing.
    if redis is not None and pricing.billing_unit_type:
        pipe = redis.pipeline()
        pipe.hset(cache_key, mapping={
            "billing_unit_type": pricing.billing_unit_type,
            "unit_rate": str(pricing.unit_rate) if pricing.unit_rate is not None else "",
            "cost_per_unit": str(pricing.cost_per_unit) if pricing.cost_per_unit is not None else "",
            "unit_size": str(pricing.unit_size) if pricing.unit_size is not None else "",
        })
        pipe.expire(cache_key, _PRICING_CACHE_TTL)
        await pipe.execute()

    return pricing


def calculate_cost(total_units: int, pricing: ServicePricing) -> Decimal:
    """
    ₹ cost for total_units.
    unit_rate (₹/unit) takes precedence; falls back to cost_per_unit / unit_size.
    Returns 0 when pricing fields are absent.
    """
    if pricing.unit_rate:
        return Decimal(total_units) * pricing.unit_rate
    if pricing.cost_per_unit and pricing.unit_size:
        return (Decimal(total_units) / pricing.unit_size) * pricing.cost_per_unit
    return Decimal(0)


async def deduct_balance(
    db: AsyncSession,
    tenant_id: str,
    cost: Decimal,
) -> WalletResult:
    """
    Deduct cost from the active tier assignment.
    Returns WalletResult with the new balance and tier_id.
    """
    result = await db.execute(
        text(
            "UPDATE ppu_tenant_tier_assignments"
            "   SET available_balance = available_balance - :cost,"
            "       updated_at = now()"
            " WHERE tenant_id = :tenant_id"
            "   AND effective_from <= now()"
            "   AND effective_to   >  now()"
            " RETURNING available_balance, tier_id"
        ),
        {"cost": cost, "tenant_id": tenant_id},
    )
    row = result.first()
    if row is None:
        logger.warning("deduct_balance: no active assignment for tenant=%s", tenant_id)
        return WalletResult(available_balance=Decimal(0), tier_id=None, exhausted=True)
    return WalletResult(
        available_balance=row.available_balance,
        tier_id=str(row.tier_id),
        exhausted=row.available_balance <= 0,
    )


async def update_quota_usage(
    db: AsyncSession,
    tenant_id: str,
    inference_name: str,
    billing_month: str,
    tier_id: str,
    units: int,
) -> bool:
    """
    UPSERT quota usage for this tenant/inference_name/month.
    Returns True if quota is now exhausted, False if unlimited or under cap.
    """
    snap_result = await db.execute(
        text(
            "SELECT monthly_quota FROM ppu_tier_quotas"
            " WHERE tier_id = :tier_id AND inference_name = :inference_name"
        ),
        {"tier_id": tier_id, "inference_name": inference_name},
    )
    snap = snap_result.scalar()
    if snap is None:
        return False  # no cap for this tier + type

    result = await db.execute(
        text(
            "INSERT INTO ppu_quota_usage"
            "  (id, tenant_id, inference_name, billing_month, monthly_quota_snap, units_used)"
            " VALUES"
            "  (gen_random_uuid(), :tenant_id, :inference_name, :billing_month, :snap, :units)"
            " ON CONFLICT (tenant_id, inference_name, billing_month)"
            " DO UPDATE SET units_used = ppu_quota_usage.units_used + EXCLUDED.units_used"
            " RETURNING units_used, monthly_quota_snap"
        ),
        {
            "tenant_id": tenant_id,
            "inference_name": inference_name,
            "billing_month": billing_month,
            "snap": snap,
            "units": units,
        },
    )
    row = result.first()
    return row is not None and row.units_used >= row.monthly_quota_snap
