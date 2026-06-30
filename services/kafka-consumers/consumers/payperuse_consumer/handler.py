import json
from datetime import datetime, timezone

import httpx
from confluent_kafka.cimpl import Message

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
        return

    attrs = data.get("attributes") or {}

    # tenantId is camelCase in OTel attributes (set by ai4i_core.context middleware).
    tenant_id: str = str(attrs.get("tenantId") or "").strip()
    service_id: str = str(attrs.get("service_id") or "").strip()
    input_tokens: int = int(attrs.get("input_tokens") or 0)
    output_tokens: int = int(attrs.get("output_tokens") or 0)
    total_tokens: int = input_tokens + output_tokens
    end_time_ns = data.get("end_time")

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

    async with db_registry.get_session(settings.db_settings.PLATFORM_CORE_DB) as db:
        pricing: ServicePricing | None = await get_service_pricing(db, service_id)
        if pricing is None:
            logger.warning(
                "No pricing found for service_id=%s — skipping billing for tenant=%s",
                service_id, tenant_id,
            )
            return

        cost = calculate_cost(total_tokens, pricing)
        if cost == 0:
            logger.warning(
                "Zero cost for service_id=%s — skipping billing for tenant=%s",
                service_id, tenant_id,
            )
            return

        wallet = await deduct_balance(db, tenant_id, cost)

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

        # Commit DB changes before any HTTP calls to avoid holding row locks
        # across slow or failing auth-service requests.
        await db.commit()

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
