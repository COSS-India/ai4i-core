"""Billing helpers for the pay-per-use Kafka consumer."""
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ai4i_core.bootstrap import get_redis_client
from ai4i_core.logging import get_logger
from confluent_kafka.cimpl import Message
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import Constants

logger = get_logger(__name__)


@dataclass
class ServicePricing:
    task_type: str   # "llm", "asr", "nmt" — maps to inference_name
    unit_rate: Optional[Decimal]       # ₹ per single raw unit (preferred)
    cost_per_unit: Optional[Decimal]   # ₹ per unit_size units (fallback)
    unit_size: Optional[int]           # scaling divisor


@dataclass
class WalletResult:
    available_balance: Decimal
    tier_id: Optional[str]
    exhausted: bool  # balance <= 0 or no active assignment


@dataclass
class QuotaUsageResult:
    exhausted: bool
    recorded: bool  # True iff a ppu_quota_usage row was actually written this call


async def get_service_pricing(
    db: AsyncSession,
    service_id: str,
) -> Optional[ServicePricing]:
    """Return pricing for service_id; checks Redis cache before hitting DB."""
    try:
        redis = get_redis_client()
    except RuntimeError:
        redis = None
    cache_key = f"{Constants.PPU_PRICING_CACHE_PREFIX}{service_id}"

    if redis is not None:
        cached = await redis.hgetall(cache_key)
        if cached:
            return ServicePricing(
                task_type=cached.get("task_type", ""),
                unit_rate=Decimal(cached["unit_rate"]) if cached.get("unit_rate") else None,
                cost_per_unit=Decimal(cached["cost_per_unit"]) if cached.get("cost_per_unit") else None,
                unit_size=int(cached["unit_size"]) if cached.get("unit_size") else None,
            )

    result = await db.execute(
        text(
            "SELECT task_type, unit_rate, cost_per_unit, unit_size"
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
        task_type=row.task_type or "",
        unit_rate=Decimal(str(row.unit_rate)) if row.unit_rate is not None else None,
        cost_per_unit=Decimal(str(row.cost_per_unit)) if row.cost_per_unit is not None else None,
        unit_size=int(row.unit_size) if row.unit_size else None,
    )

    # Only cache when the service has a task_type configured; otherwise
    # a stale empty entry would block billing for 1 hour after admin adds pricing.
    if redis is not None and pricing.task_type:
        pipe = redis.pipeline()
        pipe.hset(cache_key, mapping={
            "task_type": pricing.task_type,
            "unit_rate": str(pricing.unit_rate) if pricing.unit_rate is not None else "",
            "cost_per_unit": str(pricing.cost_per_unit) if pricing.cost_per_unit is not None else "",
            "unit_size": str(pricing.unit_size) if pricing.unit_size is not None else "",
        })
        pipe.expire(cache_key, Constants.PPU_PRICING_CACHE_TTL)
        await pipe.execute()

    return pricing


def calculate_cost(total_units: Decimal, pricing: ServicePricing) -> Decimal:
    """
    ₹ cost for total_units.
    unit_rate (₹/unit) takes precedence; falls back to cost_per_unit / unit_size.
    Returns 0 when pricing fields are absent.
    """
    if pricing.unit_rate:
        return total_units * pricing.unit_rate
    if pricing.cost_per_unit and pricing.unit_size:
        return (total_units / pricing.unit_size) * pricing.cost_per_unit
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
    units: Decimal,
    cost: Decimal,
) -> QuotaUsageResult:
    """
    UPSERT quota usage for this tenant/inference_name/month/tier.
    Accumulates units_used and cost_accum within the active tier's row. If the
    tenant's active tier changes mid-month (see tenant_assignment_service.
    reassign_tier), this starts a fresh row for the new tier rather than
    folding into the previous tier's accumulated numbers.

    ``recorded=False`` means no ppu_tier_quotas row exists for this
    tier/tasktype, so nothing was written to ppu_quota_usage — exhausted is
    still True in that case (not entitled), but callers must not log it as
    an upsert.
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
        # No ppu_tier_quotas row means this tasktype isn't part of the tier's
        # mapping at all — not entitled, not "unlimited". Treat as exhausted so
        # _post_billing marks quota-{inference_name} and future requests to this
        # tasktype are blocked by quota_guard.
        logger.warning(
            "update_quota_usage: tasktype not included in tier — tier_id=%s"
            " inference_name=%s — marking quota exhausted",
            tier_id, inference_name,
        )
        return QuotaUsageResult(exhausted=True, recorded=False)

    result = await db.execute(
        text(
            "INSERT INTO ppu_quota_usage"
            "  (id, tenant_id, inference_name, billing_month, monthly_quota_snap,"
            "   units_used, tier_id, cost_accum)"
            " VALUES"
            "  (gen_random_uuid(), :tenant_id, :inference_name, :billing_month, :snap,"
            "   :units, :tier_id, :cost)"
            " ON CONFLICT (tenant_id, inference_name, billing_month, tier_id)"
            " DO UPDATE SET units_used = ppu_quota_usage.units_used + EXCLUDED.units_used,"
            "               cost_accum = ppu_quota_usage.cost_accum + EXCLUDED.cost_accum,"
            "               updated_at = now()"
            " RETURNING units_used, monthly_quota_snap"
        ),
        {
            "tenant_id": tenant_id,
            "inference_name": inference_name,
            "billing_month": billing_month,
            "snap": snap,
            "units": units,
            "tier_id": tier_id,
            "cost": cost,
        },
    )
    row = result.first()
    exhausted = row is not None and row.units_used >= row.monthly_quota_snap
    return QuotaUsageResult(exhausted=exhausted, recorded=True)


def _get_billing_data(message: Message) -> Optional[dict]:
    payload_bytes = message.value()
    logger.info(
        "Message received | topic=%s partition=%d offset=%d size=%d bytes",
        message.topic(),
        message.partition(),
        message.offset(),
        len(payload_bytes) if payload_bytes else 0,
    )

    if not payload_bytes:
        logger.warning("Empty message payload — skipping offset=%d", message.offset())
        return None

    try:
        data = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Kafka message as JSON: %s", exc)
        return None

    # Only process ai-inference spans — the model and request spans are noise for billing.
    span_name = data.get("name", "")
    if span_name != "ai-inference":
        logger.debug("Skipping non-billing span | span_name=%r offset=%d", span_name, message.offset())
        return None

    return data


def _get_billed_key(correlation_id: str, span_id: str) -> str:
    return f"{Constants.PPU_BILLED_KEY_PREFIX}{correlation_id}:{span_id}" if correlation_id else ""


async def _update_billing_on_cache(is_already_billed: bool, billed_key: str, correlation_id: str) -> None:
    # Do not change the following strict check of False to not(is_already_billed)
    # noinspection PySimplifyBooleanCheck
    if is_already_billed is False:
        try:
            redis = get_redis_client()
            await redis.set(billed_key, "1", ex=Constants.PPU_BILLED_KEY_TTL)
        except Exception as exc:
            logger.warning(
                "Failed to set Redis dedup key for correlation_id=%s: %s",
                correlation_id, exc,
            )