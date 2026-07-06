from datetime import datetime, timezone

import httpx
from ai4i_core.bootstrap import get_redis_client
from ai4i_core.logging import get_logger
from confluent_kafka.cimpl import Message

from config import settings
from consumers.payperuse_consumer._billing import (
    deduct_balance,
    update_quota_usage,
    _get_billing_data,
    _get_pricing_and_cost,
    _get_billed_key, _update_billing_on_cache,
)
from consumers.registry import kafka_listener
from db_registry import db_registry

logger = get_logger(__name__)


def _get_otel_attributes(attrs: dict):
    tenant_id: str = str(attrs.get("tenantId") or "").strip()
    service_id: str = str(attrs.get("service_id") or "").strip()
    input_tokens: int = int(attrs.get("input_tokens") or 0)
    output_tokens: int = int(attrs.get("output_tokens") or 0)
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


@kafka_listener(settings.topics.TOPIC_PAY_PER_USE)
async def handle_ppu_usage(msg: Message) -> None:
    data: dict | None = _get_billing_data(msg)
    if not data:
        return
    span_id: str = (data.get("context", {})).get("span_id", "").strip()

    # Deduplicate using correlation_id — the application-level request identifier
    # injected by RequestMiddleware and stored as a span attribute.  It is unique
    # per request and stable across Kafka redeliveries, so it makes a reliable
    # dedup key.  We deliberately avoid span_id: OTel may emit 0x000…0 for spans
    # with an invalid OTel context, and every span sharing that value would map to
    # the same Redis key — poisoning the dedup set after the first hit.
    attrs = data.get("attributes", {})
    # tenantId is camelCase in OTel attributes (set by ai4i_core.context middleware).
    tenant_id, service_id, input_tokens, output_tokens, correlation_id = _get_otel_attributes(attrs)
    billed_key: str = _get_billed_key(correlation_id)

    is_already_billed = await _is_already_billed(billed_key, correlation_id, span_id, msg)
    if is_already_billed or is_already_billed is None:
        return
    # Skip billing for JWT / non-API-key requests. authType is set by RequestMiddleware
    # from the X-Auth-Type header injected by APISIX after token validation.
    # Only "api_key" requests are subject to PPU billing. If authType is absent
    # (older spans without this attribute), billing proceeds as before.
    auth_type: str = str(attrs.get("authType", "")).strip()
    if auth_type and auth_type != "api_key":
        logger.info(
            "Skipping billing for non-API-key request | auth_type=%r offset=%d span_id=%s",
            auth_type, msg.offset(), span_id,
        )
        return

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
        pricing, cost = await _get_pricing_and_cost(db, service_id, tenant_id, total_tokens)
        if not (pricing and cost):
            return
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

    # using is_already_billed to carryout setting of billing details to redis,
    await _update_billing_on_cache(is_already_billed, billed_key, correlation_id)

    logger.info(
        "Billing applied | tenant=%s service=%s tokens=%d cost=%s exhausted=%s",
        tenant_id, service_id, total_tokens, cost, wallet.exhausted,
    )
    await _post_billing(wallet.exhausted, quota_exhausted, tenant_id, pricing.billing_unit_type)


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
