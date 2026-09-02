"""Billing helpers for the pay-per-use Kafka consumer."""
import json
import time
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


# Process-local memo for the DB-fallback path, keyed by lowercased name.
# Bounded by the size of the catalogue (~12 rows), so no eviction policy needed.
_inference_type_ids: dict[str, tuple[Optional[int], float]] = {}


async def get_inference_type_id(db: AsyncSession, inference_name: str) -> Optional[int]:
    """Resolve inference_type_id for a task type; Redis, then memo, then DB.

    Reads ``core:inference_type:<name>`` — written by platform-core's
    ``inference_type_cache``, a cross-service contract (both services must
    share a Redis host and logical DB). The DB fallback is mandatory, not
    belt-and-braces: these keys live under allkeys-lru pressure, and a
    cache-only path would silently stop resolving ids under memory pressure.

    This function deliberately does **not** write back to Redis. Those keys hold
    the whole catalogue row and platform-core reads them expecting that shape;
    writing a partial ``{"id": n}`` from here would corrupt them. platform-core
    stays the single writer (it warms on startup and rebuilds on every
    mutation). The process-local memo below keeps a cold Redis from costing a
    DB round-trip per message — one per task type per process instead.

    Returns None when the name is empty or absent from the catalogue. From
    phase 2 on, None means **quota cannot be enforced for this span**: the upsert
    joins and conflicts on inference_type_id, so a NULL selects no rows. The
    caller must skip the quota decision entirely and must NOT read the resulting
    quota_recorded=False as exhaustion — that would 429 every tenant on an
    otherwise-working tier. See handler._bill_usage.

    A negative result is memoised far more briefly than a positive one: under
    phase 1 a stale negative cost a NULL column value, but now it costs a window
    of unenforced quota for a type an admin has just created.
    """
    if not inference_name:
        return None
    normalized = inference_name.lower()

    try:
        redis = get_redis_client()
    except RuntimeError:
        redis = None

    cache_key = f"{Constants.INFERENCE_TYPE_CACHE_PREFIX}{normalized}"
    if redis is not None:
        try:
            # The key is a hash written by platform-core; pull only the one
            # field this needs. HGET returns None when either the key or the
            # field is absent, which falls through to the memo/DB below.
            cached_id = await redis.hget(cache_key, "id")
            if cached_id:
                return int(cached_id)
        except Exception as exc:
            logger.warning(
                "Inference type cache read failed for %s: %s", normalized, exc
            )

    memo = _inference_type_ids.get(normalized)
    if memo is not None and time.monotonic() < memo[1]:
        return memo[0]

    result = await db.execute(
        text("SELECT id FROM inference_types WHERE name = :name LIMIT 1"),
        {"name": normalized},
    )
    row = result.first()
    type_id = int(row.id) if row is not None else None
    if type_id is None:
        logger.error(
            "Inference type %r is not in the inference_types catalogue "
            "(checked Redis, process memo and the database) — quota cannot be "
            "enforced for it. Create it via POST /inference-types.",
            normalized,
            extra={"event": "ppu.inference_type.unresolved", "task_type": normalized},
        )
    ttl = (
        Constants.INFERENCE_TYPE_MEMO_TTL
        if type_id is not None
        else Constants.INFERENCE_TYPE_NEGATIVE_MEMO_TTL
    )
    _inference_type_ids[normalized] = (type_id, time.monotonic() + ttl)
    return type_id


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
    billing_month: str,
    units: Decimal,
    cost: Decimal,
    api_key_id: int = 0,
    tier_id: Optional[str] = None,
    inference_type_id: Optional[int] = None,
) -> BillingWriteResult:
    """
    Single round-trip fusing budget deduction (budget_usage) + quota upsert
    (quota_usage).

    budget_update: plain UPDATE on budget_usage keyed by api_key_id. Produces
    no row when api_key_id=0 or no budget_usage row exists for the key —
    budget tracking is silently skipped (key has no budget ceiling).

    quota_upsert: looks up monthly_quota_snap from tier_quotas using tier_id
    passed directly from the OTel span (set by auth service, propagated via
    X-Tier-ID header → context → span attribute). Produces no row when
    tier_id is None, inference_type_id is None, or tier_quotas has no matching
    (tier_id, inference_type_id) row. CAST(:tier_id AS uuid) with a SQL NULL
    evaluates the WHERE condition to UNKNOWN (never TRUE), so the INSERT selects
    no rows — safe no-op, and the same is true of a NULL inference_type_id.
    Passing an empty string instead of None would raise
    "invalid input syntax for type uuid" in Postgres; callers must normalise
    "" to None before calling (handler._get_otel_attributes does this).

    The join and the ON CONFLICT target are both keyed on inference_type_id
    . Two details that look cosmetic and are not:

      * inference_name is written from ``it.name``, not from a bound parameter.
        The retained legacy column stops being a free-text write, which is what
        keeps the old name-keyed unique constraint and the new id-keyed one
        equivalent while both exist on the table.
      * the inserted id is ``tq.inference_type_id``, not the bound parameter.
        They are equal by the join predicate, but taking it from the joined row
        makes it NOT NULL *by construction*. That is what replaces a NOT NULL
        constraint on quota_usage.inference_type_id — do not "simplify" it back
        to :inference_type_id.

    A caller that cannot resolve inference_type_id must NOT read the resulting
    quota_recorded=False as exhaustion — see handler._bill_usage, which fails
    open on a catalogue gap rather than 429ing every tenant on the tier.
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
            "      (id, tenant_id, inference_name, inference_type_id, billing_month,"
            "       monthly_quota_snap, monthly_quota_used, tier_id)"
            "    SELECT gen_random_uuid(), :tenant_id, it.name,"
            "           tq.inference_type_id, :billing_month,"
            "           tq.monthly_quota, :units, :tier_id"
            "    FROM tier_quotas tq"
            "    JOIN inference_types it ON it.id = tq.inference_type_id"
            "    WHERE tq.tier_id = CAST(:tier_id AS uuid)"
            "      AND tq.inference_type_id = CAST(:inference_type_id AS int)"
            "    ON CONFLICT (tenant_id, inference_type_id, billing_month, tier_id)"
            "    DO UPDATE SET monthly_quota_used = quota_usage.monthly_quota_used + EXCLUDED.monthly_quota_used,"
            "                  inference_name = EXCLUDED.inference_name,"
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
            "inference_type_id": inference_type_id,
            "billing_month": billing_month,
            "units": units,
            "cost": cost,
            "tier_id": tier_id,
        },
    )
    row = result.first()

    budget_used = row.api_key_budget_used if row and row.api_key_budget_used is not None else Decimal(0)
    budget_snap = row.api_key_budget_snap if row and row.api_key_budget_snap is not None else None
    tier_id_from_row = str(row.tier_id) if row and row.tier_id is not None else None
    tier_id = tier_id_from_row or tier_id or None

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
