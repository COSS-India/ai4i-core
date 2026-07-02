import json
from datetime import datetime, timezone

import httpx
from confluent_kafka.cimpl import Message

from ai4i_core.bootstrap import get_redis_client
from ai4i_core.logging import get_logger
from config import settings
from consumers.registry import kafka_listener
from db_registry import db_registry

from consumers.payperuse_consumer._billing import (
    ServicePricing,
    calculate_cost,
    deduct_balance,
    get_service_pricing,
    update_quota_usage,
)

logger = get_logger(__name__)

_BILLED_KEY_PREFIX = "ppu:billed:"
_BILLED_KEY_TTL = 86400  # 24 hours — longer than any realistic Kafka redelivery window


@kafka_listener(settings.topics.TOPIC_PAY_PER_USE)
async def handle_ppu_usage(msg: Message) -> None:
    payload_bytes = msg.value()
    logger.info(
        "Message received | topic=%s partition=%d offset=%d size=%d bytes",
        msg.topic(),
        msg.partition(),
        msg.offset(),
        len(payload_bytes) if payload_bytes else 0,
    )

    if not payload_bytes:
        logger.warning("Empty message payload — skipping offset=%d", msg.offset())
        return

    try:
        data = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Kafka message as JSON: %s", exc)
        return

    # Only process ai-inference spans — the model and request spans are noise for billing.
    span_name = data.get("name", "")
    if span_name != "ai-inference":
        logger.debug("Skipping non-billing span | span_name=%r offset=%d", span_name, msg.offset())
        return

    # Deduplicate using the OTel span_id — unique per inference span.
    # Guards against double-billing when Kafka redelivers after a rebalance.
    span_id: str = (data.get("context") or {}).get("span_id", "").strip()
    if span_id:
        try:
            redis = get_redis_client()
            billed_key = f"{_BILLED_KEY_PREFIX}{span_id}"
            already_billed = await redis.exists(billed_key)
            if already_billed:
                logger.warning(
                    "Duplicate span detected — skipping billing offset=%d span_id=%s",
                    msg.offset(), span_id,
                )
                return
        except Exception as exc:
            # Redis unavailable: log and continue — billing correctness relies on
            # at-most-one consumer instance when Redis is down.
            logger.warning("Redis dedup check failed — proceeding without dedup: %s", exc)
            span_id = ""  # don't attempt the post-commit SET either

    attrs = data.get("attributes") or {}

    # Skip billing for JWT / non-API-key requests. authType is set by RequestMiddleware
    # from the X-Auth-Type header injected by APISIX after token validation.
    # Only "api_key" requests are subject to PPU billing. If authType is absent
    # (older spans without this attribute), billing proceeds as before.
    auth_type: str = str(attrs.get("authType") or "").strip()
    if auth_type and auth_type != "api_key":
        logger.info(
            "Skipping billing for non-API-key request | auth_type=%r offset=%d span_id=%s",
            auth_type, msg.offset(), span_id,
        )
        return

    # tenantId is camelCase in OTel attributes (set by ai4i_core.context middleware).
    tenant_id: str = str(attrs.get("tenantId") or "").strip()
    service_id: str = str(attrs.get("service_id") or "").strip()
    input_tokens: int = int(attrs.get("input_tokens") or 0)
    output_tokens: int = int(attrs.get("output_tokens") or 0)
    total_tokens: int = input_tokens + output_tokens
    end_time_ns = data.get("end_time")

    logger.info(
        "Billing fields extracted | offset=%d tenant_id=%r service_id=%r"
        " input_tokens=%d output_tokens=%d total_tokens=%d span_id=%s",
        msg.offset(), tenant_id, service_id, input_tokens, output_tokens, total_tokens, span_id,
    )

    if not (tenant_id and service_id and total_tokens):
        logger.warning(
            "Missing required billing fields — skipping offset=%d"
            " (tenant_id=%r service_id=%r total_tokens=%d)",
            msg.offset(), tenant_id, service_id, total_tokens,
        )
        return

    billing_month = (
        datetime.fromtimestamp(int(end_time_ns) / 1e9, tz=timezone.utc).strftime("%Y-%m")
        if end_time_ns
        else datetime.now(timezone.utc).strftime("%Y-%m")
    )
    logger.info("Billing month resolved | tenant=%s billing_month=%s", tenant_id, billing_month)

    async with db_registry.get_session(settings.db_settings.PLATFORM_CORE_DB) as db:
        pricing: ServicePricing | None = await get_service_pricing(db, service_id)
        if pricing is None:
            logger.warning(
                "No pricing found for service_id=%s — skipping billing for tenant=%s",
                service_id, tenant_id,
            )
            return

        logger.info(
            "Pricing resolved | service_id=%s billing_unit_type=%r"
            " unit_rate=%s cost_per_unit=%s unit_size=%s",
            service_id, pricing.billing_unit_type,
            pricing.unit_rate, pricing.cost_per_unit, pricing.unit_size,
        )

        cost = calculate_cost(total_tokens, pricing)
        if cost == 0:
            logger.warning(
                "Zero cost for service_id=%s — skipping billing for tenant=%s"
                " (unit_rate=%s cost_per_unit=%s unit_size=%s)",
                service_id, tenant_id,
                pricing.unit_rate, pricing.cost_per_unit, pricing.unit_size,
            )
            return

        logger.info("Cost calculated | tenant=%s cost=%s tokens=%d", tenant_id, cost, total_tokens)

        wallet = await deduct_balance(db, tenant_id, cost)

        if wallet.tier_id is None:
            # deduct_balance already logged the warning; no active assignment means
            # nothing was written — skip commit and Redis mark.
            return

        logger.info(
            "Balance deducted | tenant=%s tier_id=%s available_balance=%s exhausted=%s",
            tenant_id, wallet.tier_id, wallet.available_balance, wallet.exhausted,
        )

        quota_exhausted = False
        if wallet.tier_id and pricing.billing_unit_type:
            quota_exhausted = await update_quota_usage(
                db,
                tenant_id=tenant_id,
                inference_name=pricing.billing_unit_type,
                billing_month=billing_month,
                tier_id=wallet.tier_id,
                units=total_tokens,
            )
            logger.info(
                "Quota usage upserted | tenant=%s inference=%s billing_month=%s"
                " units=%d quota_exhausted=%s",
                tenant_id, pricing.billing_unit_type, billing_month, total_tokens, quota_exhausted,
            )
        else:
            logger.info(
                "Quota update skipped | tenant=%s tier_id=%s billing_unit_type=%r",
                tenant_id, wallet.tier_id, pricing.billing_unit_type,
            )

        # Commit DB changes before any HTTP calls to avoid holding row locks
        # across slow or failing auth-service requests.
        await db.commit()
        logger.info("DB commit successful | tenant=%s offset=%d", tenant_id, msg.offset())

    # Mark span as billed in Redis after DB commit so a crash before this point
    # causes a retry (over-billing risk) rather than silent data loss.
    if span_id:
        try:
            redis = get_redis_client()
            await redis.set(billed_key, "1", ex=_BILLED_KEY_TTL)
        except Exception as exc:
            logger.warning("Failed to set Redis dedup key for span_id=%s: %s", span_id, exc)

    logger.info(
        "Billing applied | tenant=%s service=%s tokens=%d cost=%s exhausted=%s",
        tenant_id, service_id, total_tokens, cost, wallet.exhausted,
    )

    if wallet.exhausted:
        await _notify_auth(
            f"/internal/ppu/tenant/{tenant_id}/budget-exhausted",
            {"exhausted": True},
        )

    if quota_exhausted:
        await _notify_auth(
            f"/internal/ppu/tenant/{tenant_id}/quota-exhausted",
            {"inference_name": pricing.billing_unit_type},
        )


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
