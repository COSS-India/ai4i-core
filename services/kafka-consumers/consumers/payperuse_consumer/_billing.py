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

from consumers.payperuse_consumer.config import Constants

logger = get_logger(__name__)


@dataclass
class ServicePricing:
    task_type: str   # "llm", "asr", "nmt" — maps to inference_name
    unit_rate: Optional[Decimal]       # ₹ per single raw unit (preferred)
    cost_per_unit: Optional[Decimal]   # ₹ per unit_size units (fallback)
    unit_size: Optional[int]           # scaling divisor


@dataclass
class BillingWriteResult:
    """Result of the fused wallet-deduction + quota-upsert write.

    tier_id is None when the tenant has no active tier assignment — nothing
    was written to either table (wallet_exhausted is forced False here,
    matching the caller's existing convention of using quota_exhausted
    rather than wallet_exhausted to signal "no active assignment", so a
    missing assignment doesn't fire the budget-exhausted auth-service call).

    quota_recorded=False with tier_id set means no ppu_tier_quotas row
    matches this tier/tasktype (or the caller passed an empty
    inference_name because pricing.task_type was unset) — quota_exhausted
    is True in that case as the DB-level default (not entitled), but
    callers whose pricing.task_type was empty must override it to False
    themselves, since that's a different "no quota constraint configured"
    case that's indistinguishable from "not entitled" at the SQL level
    (both yield zero matching rows).
    """
    available_balance: Decimal
    tier_id: Optional[str]
    wallet_exhausted: bool
    quota_recorded: bool
    quota_exhausted: bool


async def get_service_pricing(
    db: AsyncSession,
    service_id: str,
) -> Optional[ServicePricing]:
    """Return pricing for service_id; checks Redis cache before hitting DB."""
    try:
        redis = get_redis_client()
    except RuntimeError:
        redis = None
    cache_key = f"{Constants.PRICING_CACHE_PREFIX}{service_id}"

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
        await pipe.hset(cache_key, mapping={
            "task_type": pricing.task_type,
            "unit_rate": str(pricing.unit_rate) if pricing.unit_rate is not None else "",
            "cost_per_unit": str(pricing.cost_per_unit) if pricing.cost_per_unit is not None else "",
            "unit_size": str(pricing.unit_size) if pricing.unit_size is not None else "",
        })
        await pipe.expire(cache_key, Constants.PRICING_CACHE_TTL)
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


async def deduct_balance_and_update_quota(
    db: AsyncSession,
    tenant_id: str,
    inference_name: str,
    billing_month: str,
    units: Decimal,
    cost: Decimal,
) -> BillingWriteResult:
    """
    Single round-trip fusing what were two sequential writes:
      1. deduct_balance — debit the tenant's active tier assignment.
      2. update_quota_usage — UPSERT this tenant/inference/month/tier's
         accumulated usage, sourcing monthly_quota from ppu_tier_quotas.

    A writable-CTE chain lets both writes commit as one statement in one
    round-trip instead of two, with the same atomicity as before — both
    succeed or both roll back together with the session's transaction.

    wallet_update always attempts the deduction. quota_upsert only
    produces a row when wallet_update produced one (an active assignment
    exists) *and* ppu_tier_quotas has a matching (tier_id, inference_name)
    row — if either is missing, quota_upsert's FROM/JOIN yields zero rows,
    so nothing is inserted there, mirroring the old code's "no assignment"
    and "not entitled" branches respectively. ppu_tier_quotas has a unique
    constraint on (tier_id, inference_name), so quota_upsert never yields
    more than one row when it does match.

    inference_name='' (pricing.task_type unset) simply never matches a
    ppu_tier_quotas row either, so quota_upsert naturally does nothing in
    that case too — quota_recorded=False either way, and it's the
    caller's job to distinguish "task_type unset" (not exhausted) from
    "genuinely not entitled" (exhausted) using pricing.task_type, same as
    the old _check_quota's early return did.
    """
    result = await db.execute(
        text(
            "WITH wallet_update AS ("
            "    UPDATE ppu_tenant_tier_assignments"
            "       SET available_balance = available_balance - :cost,"
            "           updated_at = now()"
            "     WHERE tenant_id = :tenant_id"
            "       AND effective_from <= now()"
            "       AND effective_to   >  now()"
            "    RETURNING available_balance, tier_id"
            "),"
            " quota_upsert AS ("
            "    INSERT INTO quota_usage"
            "      (id, tenant_id, inference_name, billing_month, monthly_quota_snap,"
            "       monthly_quota_used, tier_id)"
            "    SELECT gen_random_uuid(), :tenant_id, :inference_name, :billing_month,"
            "           ptq.monthly_quota, :units, wallet_update.tier_id"
            "    FROM wallet_update"
            "    JOIN tier_quotas ptq"
            "      ON ptq.tier_id = wallet_update.tier_id AND ptq.inference_name = :inference_name"
            "    ON CONFLICT (tenant_id, inference_name, billing_month, tier_id)"
            "    DO UPDATE SET monthly_quota_used = quota_usage.monthly_quota_used + EXCLUDED.monthly_quota_used,"
            "                  updated_at = now()"
            "    RETURNING monthly_quota_used, monthly_quota_snap"
            " )"
            " SELECT wallet_update.available_balance, wallet_update.tier_id,"
            "        quota_upsert.monthly_quota_used, quota_upsert.monthly_quota_snap"
            " FROM wallet_update"
            " LEFT JOIN quota_upsert ON true"
        ),
        {
            "tenant_id": tenant_id,
            "inference_name": inference_name,
            "billing_month": billing_month,
            "units": units,
            "cost": cost,
        },
    )
    row = result.first()
    if row is None:
        # wallet_update itself produced no row — no active tier assignment.
        # wallet_exhausted stays False here (not True) so this doesn't fire
        # the budget-exhausted auth-service call; quota_exhausted=True is
        # the signal callers use instead to block further requests.
        logger.warning("deduct_balance: no active assignment for tenant=%s", tenant_id)
        return BillingWriteResult(
            available_balance=Decimal(0), tier_id=None,
            wallet_exhausted=False, quota_recorded=False, quota_exhausted=True,
        )

    quota_recorded = row.monthly_quota_used is not None
    # Not recorded (no tier_quotas match) defaults to exhausted=True —
    # the DB-level "not entitled" signal; empty-task_type callers override
    # this to False themselves (see the docstring above).
    quota_exhausted = (not quota_recorded) or (row.monthly_quota_used >= row.monthly_quota_snap)
    return BillingWriteResult(
        available_balance=row.available_balance,
        tier_id=str(row.tier_id),
        wallet_exhausted=row.available_balance <= 0,
        quota_recorded=quota_recorded,
        quota_exhausted=quota_exhausted,
    )


def _get_billing_data(message: Message) -> Optional[dict]:
    payload_bytes = message.value()
    logger.debug(
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
    return f"{Constants.BILLED_KEY_PREFIX}{correlation_id}:{span_id}" if correlation_id else ""


async def _update_billing_on_cache(is_already_billed: bool, billed_key: str, correlation_id: str) -> None:
    # Do not change the following strict check of False to not(is_already_billed)
    # noinspection PySimplifyBooleanCheck
    if is_already_billed is False:
        try:
            redis = get_redis_client()
            await redis.set(billed_key, "1", ex=Constants.BILLED_KEY_TTL)
        except Exception as exc:
            logger.warning(
                "Failed to set Redis dedup key for correlation_id=%s: %s",
                correlation_id, exc,
            )
