from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
from ai4i_core.bootstrap import get_redis_client
from ai4i_core.logging import get_logger
from confluent_kafka.cimpl import Message

from config import settings
from consumers.payperuse_consumer._billing import (
    ServicePricing,
    calculate_cost,
    deduct_balance_and_update_quota,
    get_service_pricing,
    _get_billing_data,
    _get_billed_key, _update_billing_on_cache,
)
from consumers.registry import kafka_listener
from db_registry import db_registry

logger = get_logger(__name__)


def _get_otel_attributes(attrs: dict):
    tenant_id: str = str(attrs.get("tenantId") or "").strip()
    service_id: str = str(attrs.get("service_id") or "").strip()
    # Both LLM and Triton spans write real counts to input_tokens/output_tokens
    # (see trace/request_span.py and services/base/task_service.py).
    input_tokens: float = float(attrs.get("input_tokens") or 0)
    output_tokens: float = float(attrs.get("output_tokens") or 0)
    correlation_id: str = str(attrs.get("correlation_id") or "").strip()

    return tenant_id, service_id, input_tokens, output_tokens, correlation_id


async def _is_already_billed(billed_key: str, correlation_id: str, span_id: str, msg: Message) -> bool | None:
    if not billed_key:
        return None
    try:
        redis = get_redis_client()
        already_billed = await redis.exists(billed_key)
        if already_billed:
            logger.warning(
                "Duplicate span detected — skipping billing offset=%d"
                " correlation_id=%s span_id=%s",
                msg.offset(), correlation_id, span_id,
            )
            return True
        return False
    except Exception as exc:
        # Redis unavailable: log and continue — billing correctness relies on
        # at-most-one consumer instance when Redis is down.
        logger.warning("Redis dedup check failed — proceeding without dedup: %s", exc)
        return None


async def _post_billing(wallet_exhausted: bool, quota_exhausted: bool, tenant_id, billing_unit_type: str):
    if wallet_exhausted:
        await _notify_auth(
            f"/internal/ppu/tenant/{tenant_id}/budget-exhausted",
            {"exhausted": True},
        )

    if quota_exhausted:
        await _notify_auth(
            f"/internal/ppu/tenant/{tenant_id}/quota-exhausted",
            {"inference_name": billing_unit_type},
        )


@dataclass
class BillingContext:
    tenant_id: str
    service_id: str
    input_tokens: float
    total_tokens: float
    correlation_id: str
    span_id: str
    billed_key: str
    is_already_billed: bool
    billing_month: str
    offset: int


@dataclass
class BillingOutcome:
    pricing: ServicePricing
    billed_units: Decimal
    cost: Decimal
    wallet_exhausted: bool
    quota_exhausted: bool


def _resolve_billing_month(end_time_ns) -> str:
    if end_time_ns:
        return datetime.fromtimestamp(int(end_time_ns) / 1e9, tz=timezone.utc).strftime("%Y-%m")
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _prepare_billing_context(msg: Message) -> Optional[BillingContext]:
    data: dict | None = _get_billing_data(msg)
    if not data:
        return None

    span_id: str = (data.get("context", {})).get("span_id", "").strip()

    # Deduplicate on correlation_id + span_id, not correlation_id alone.
    # correlation_id is the application-level request identifier injected by
    # RequestMiddleware — stable across Kafka redeliveries of the *same* span,
    # which is what makes it useful for dedup. But a single request can emit
    # multiple ai-inference spans sharing one correlation_id (e.g. TTS chunks
    # text >400 chars into several per_item Triton calls, each its own span —
    # see tts_service.py). Keying on correlation_id alone would make every
    # chunk after the first look like a duplicate of it and get skipped,
    # silently under-billing the request. span_id disambiguates chunks while
    # correlation_id still catches true redeliveries of the same span. The
    # exporter (trace/setup.py) already drops spans with span_id==0, so every
    # span_id reaching this consumer is valid and unique.
    attrs = data.get("attributes", {})
    # tenantId is camelCase in OTel attributes (set by ai4i_core.context middleware).
    tenant_id, service_id, input_tokens, output_tokens, correlation_id = _get_otel_attributes(attrs)
    billed_key: str = _get_billed_key(correlation_id, span_id)

    is_already_billed = await _is_already_billed(billed_key, correlation_id, span_id, msg)
    if is_already_billed or is_already_billed is None:
        return None

    # Skip billing for JWT / non-API-key requests. authType is set by RequestMiddleware
    # from the X-Auth-Type header injected by APISIX after token validation.
    # Only "api_key" requests are subject to PPU billing. If authType is absent
    # (older spans without this attribute), billing proceeds as before.
    auth_type: str = str(attrs.get("authType", "")).strip()
    if auth_type and auth_type != "api_key":
        logger.debug(
            "Skipping billing for non-API-key request | auth_type=%r offset=%d span_id=%s",
            auth_type, msg.offset(), span_id,
        )
        return None

    total_tokens: float = input_tokens + output_tokens

    logger.debug(
        "Billing fields extracted | offset=%d tenant_id=%r service_id=%r"
        " input_tokens=%s output_tokens=%s total_tokens=%s span_id=%s",
        msg.offset(), tenant_id, service_id, input_tokens, output_tokens, total_tokens, span_id,
    )

    if not (tenant_id and service_id and total_tokens):
        logger.warning(
            "Missing required billing fields — skipping offset=%d"
            " (tenant_id=%r service_id=%r total_tokens=%s)",
            msg.offset(), tenant_id, service_id, total_tokens,
        )
        return None

    billing_month = _resolve_billing_month(data.get("end_time"))
    logger.debug("Billing month resolved | tenant=%s billing_month=%s", tenant_id, billing_month)

    return BillingContext(
        tenant_id=tenant_id,
        service_id=service_id,
        input_tokens=input_tokens,
        total_tokens=total_tokens,
        correlation_id=correlation_id,
        span_id=span_id,
        billed_key=billed_key,
        is_already_billed=is_already_billed,
        billing_month=billing_month,
        offset=msg.offset(),
    )


async def _bill_usage(db, ctx: BillingContext) -> Optional[BillingOutcome]:
    pricing: ServicePricing | None = await get_service_pricing(db, ctx.service_id)
    if pricing is None:
        logger.warning(
            "No pricing found for service_id=%s — skipping billing for tenant=%s",
            ctx.service_id, ctx.tenant_id,
        )
        return None

    logger.debug(
        "Pricing resolved | service_id=%s task_type=%r"
        " unit_rate=%s cost_per_unit=%s unit_size=%s",
        ctx.service_id, pricing.task_type,
        pricing.unit_rate, pricing.cost_per_unit, pricing.unit_size,
    )

    # Only llm bills on input+output (real prompt/completion tokens from the
    # model's own API response). Every other inference type is input-only —
    # output_tokens is still recorded on the span for trace/observability
    # purposes, but must not count toward cost or quota here. task_type is
    # sourced from mm_services (via get_service_pricing), so it must be
    # configured correctly on the service for billing to be accurate.
    billed_units = Decimal(str(ctx.total_tokens if pricing.task_type.lower() == "llm" else ctx.input_tokens))

    cost = calculate_cost(billed_units, pricing)
    if cost == 0:
        logger.warning(
            "Zero cost for service_id=%s — skipping billing for tenant=%s"
            " (unit_rate=%s cost_per_unit=%s unit_size=%s)",
            ctx.service_id, ctx.tenant_id,
            pricing.unit_rate, pricing.cost_per_unit, pricing.unit_size,
        )
        return None

    logger.debug("Cost calculated | tenant=%s cost=%s billed_units=%s", ctx.tenant_id, cost, billed_units)

    # Fused single round-trip: balance deduction + quota upsert (see
    # deduct_balance_and_update_quota's docstring). It can't tell "task_type
    # unset" apart from "genuinely not entitled" on its own — both look like
    # zero matching ppu_tier_quotas rows to it — so that distinction is
    # applied here instead, same as the old _check_quota's early return.
    write = await deduct_balance_and_update_quota(
        db,
        tenant_id=ctx.tenant_id,
        inference_name=pricing.task_type,
        billing_month=ctx.billing_month,
        units=billed_units,
        cost=cost,
    )

    if write.tier_id is None:
        # deduct_balance_and_update_quota already logged the warning; no
        # active assignment means nothing was written to either table. The
        # tenant can't be served this tasktype right now — mark quota (not
        # wallet) exhausted so quota_guard blocks further requests, the same
        # signal used for any other quota-exhausted case.
        wallet_exhausted = False
        quota_exhausted = True
    else:
        logger.debug(
            "Balance deducted | tenant=%s tier_id=%s available_balance=%s exhausted=%s",
            ctx.tenant_id, write.tier_id, write.available_balance, write.wallet_exhausted,
        )
        wallet_exhausted = write.wallet_exhausted

        if not pricing.task_type:
            logger.debug(
                "Quota update skipped | tenant=%s tier_id=%s task_type=%r",
                ctx.tenant_id, write.tier_id, pricing.task_type,
            )
            quota_exhausted = False
        elif write.quota_recorded:
            logger.debug(
                "Quota usage upserted | tenant=%s inference=%s billing_month=%s"
                " units=%s quota_exhausted=%s",
                ctx.tenant_id, pricing.task_type, ctx.billing_month, billed_units, write.quota_exhausted,
            )
            quota_exhausted = write.quota_exhausted
        else:
            logger.debug(
                "Quota check: tasktype not mapped to tier | tenant=%s tier_id=%s"
                " inference=%s quota_exhausted=%s",
                ctx.tenant_id, write.tier_id, pricing.task_type, write.quota_exhausted,
            )
            quota_exhausted = write.quota_exhausted

    # Commit DB changes before any HTTP calls to avoid holding row locks
    # across slow or failing auth-service requests. A no-op (no rows touched)
    # when write.tier_id was None above.
    await db.commit()
    logger.debug("DB commit successful | tenant=%s offset=%d", ctx.tenant_id, ctx.offset)

    return BillingOutcome(
        pricing=pricing,
        billed_units=billed_units,
        cost=cost,
        wallet_exhausted=wallet_exhausted,
        quota_exhausted=quota_exhausted,
    )


@kafka_listener(settings.topics.TOPIC_PAY_PER_USE)
async def handle_ppu_usage(msg: Message) -> None:
    ctx = await _prepare_billing_context(msg)
    if ctx is None:
        return

    async with db_registry.get_session(settings.db_settings.PLATFORM_CORE_DB) as db:
        outcome = await _bill_usage(db, ctx)

    if outcome is None:
        return

    # Mark span as billed in Redis after DB commit so a crash before this point
    # causes a retry (over-billing risk) rather than silent data loss. Marked
    # unconditionally (including the no-tier case in _bill_usage) so a Kafka
    # redelivery of the same span doesn't re-fire the auth-service notification.
    await _update_billing_on_cache(ctx.is_already_billed, ctx.billed_key, ctx.correlation_id)

    logger.info(
        "Billing applied | tenant=%s service=%s billed_units=%s cost=%s exhausted=%s",
        ctx.tenant_id, ctx.service_id, outcome.billed_units, outcome.cost, outcome.wallet_exhausted,
    )
    await _post_billing(outcome.wallet_exhausted, outcome.quota_exhausted, ctx.tenant_id, outcome.pricing.task_type)


async def _notify_auth(path: str, body: dict) -> None:
    """POST to auth-service internal endpoint to update API key Redis flags."""
    url = f"{settings.AUTH_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
    except Exception as exc:
        # Log and continue — billing event must not fail over a notification error.
        logger.error("Failed to notify auth-service %s: %s", url, exc)
