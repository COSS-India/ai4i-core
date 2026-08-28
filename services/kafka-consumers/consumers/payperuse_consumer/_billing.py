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
    """Result of the fused budget-deduction + quota-upsert write.

    tier_id is None when the span carried no tier_id (non-API-key request or
    missing header) — quota_upsert produces no row. budget_exhausted is False
    when api_key_id is 0/absent (no budget row to check) or when the key has
    no snap set (NULL ceiling = unlimited).

    quota_recorded=False with tier_id set means no tier_quotas row matches
    this tier/tasktype — quota_exhausted defaults to True ("not entitled"),
    but callers whose pricing.task_type was empty must override it to False.
    """
    api_key_budget_used: Decimal
    api_key_budget_snap: Optional[Decimal]
    tier_id: Optional[str]
    budget_exhausted: bool
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
    api_key_id: int = 0,
    tier_id: str = "",
) -> BillingWriteResult:
    """
    Single round-trip fusing budget deduction (budget_usage) + quota upsert
    (quota_usage).

    budget_update: plain UPDATE on budget_usage keyed by api_key_id. Produces
    no row when api_key_id=0 or no budget_usage row exists for the key —
    budget tracking is silently skipped (key has no budget ceiling).

    quota_upsert: looks up monthly_quota_snap from tier_quotas using tier_id
    passed directly from the OTel span (set by auth service, propagated via
    X-Tier-ID header → context → span attribute). Produces no row when tier_id
    is empty or tier_quotas has no matching (tier_id, inference_name) row.
    """
    result = await db.execute(
        text(
            "WITH budget_update AS ("
            "    UPDATE budget_usage"
            "       SET api_key_budget_used = api_key_budget_used + :cost,"
            "           updated_at = now()"
            "     WHERE api_key_id = :api_key_id"
            "    RETURNING api_key_budget_used, api_key_budget_snap"
            "),"
            " quota_upsert AS ("
            "    INSERT INTO quota_usage"
            "      (id, tenant_id, inference_name, billing_month, monthly_quota_snap,"
            "       monthly_quota_used, tier_id)"
            "    SELECT gen_random_uuid(), :tenant_id, CAST(:inference_name AS text), :billing_month,"
            "           tq.monthly_quota, :units, :tier_id"
            "    FROM tier_quotas tq"
            "    WHERE tq.tier_id = CAST(:tier_id AS uuid) AND tq.inference_name = CAST(:inference_name AS text)"
            "    ON CONFLICT (tenant_id, inference_name, billing_month, tier_id)"
            "    DO UPDATE SET monthly_quota_used = quota_usage.monthly_quota_used + EXCLUDED.monthly_quota_used,"
            "                  updated_at = now()"
            "    RETURNING monthly_quota_used, monthly_quota_snap, tier_id"
            " )"
            " SELECT budget_update.api_key_budget_used, budget_update.api_key_budget_snap,"
            "        quota_upsert.monthly_quota_used, quota_upsert.monthly_quota_snap,"
            "        quota_upsert.tier_id"
            " FROM (SELECT 1) _dual"
            " LEFT JOIN budget_update ON true"
            " LEFT JOIN quota_upsert ON true"
        ),
        {
            "api_key_id": api_key_id,
            "tenant_id": tenant_id,
            "inference_name": inference_name,
            "billing_month": billing_month,
            "units": units,
            "cost": cost,
            "tier_id": tier_id or None,
        },
    )
    row = result.first()

    budget_used = row.api_key_budget_used if row and row.api_key_budget_used is not None else Decimal(0)
    budget_snap = row.api_key_budget_snap if row and row.api_key_budget_snap is not None else None
    tier_id = str(row.tier_id) if row and row.tier_id is not None else None

    if tier_id is None:
        logger.warning("deduct_balance: tenant=%s has no active tier — quota upsert skipped", tenant_id)

    budget_exhausted = (
        budget_snap is not None and budget_used >= budget_snap
    )

    quota_recorded = row is not None and row.monthly_quota_used is not None
    quota_exhausted = (not quota_recorded) or (row.monthly_quota_used >= row.monthly_quota_snap)

    return BillingWriteResult(
        api_key_budget_used=budget_used,
        api_key_budget_snap=budget_snap,
        tier_id=tier_id,
        budget_exhausted=budget_exhausted,
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
