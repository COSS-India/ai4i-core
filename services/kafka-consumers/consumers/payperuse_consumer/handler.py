import json

from confluent_kafka.cimpl import Message

from ai4i_core.logging import get_logger
from config import settings
from consumers.registry import kafka_listener
from db_registry import db_registry

from consumers.payperuse_consumer._billing import (
    calculate_cost,
    deduct_balance,
    get_service_pricing,
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

    model_block = data.get("model") or {}
    inference_block = data.get("ai-inference") or {}

    tenant_id: str = str(model_block.get("tenant_id") or "").strip()
    service_id: str = str(model_block.get("service_id") or "").strip()
    input_tokens: int = int(inference_block.get("input_tokens") or 0)
    output_tokens: int = int(inference_block.get("output_tokens") or 0)
    total_tokens: int = input_tokens + output_tokens

    if not (
        tenant_id and
        service_id and
        output_tokens and
        input_tokens
    ):
        logger.warning(
            "Missing tenant_id or service_id in message — skipping offset=%d",
            msg.offset(),
        )
        return

    if total_tokens == 0:
        logger.warning(
            "Zero tokens for tenant=%s service=%s — skipping offset=%d",
            tenant_id, service_id, msg.offset(),
        )
        return

    async with db_registry.get_session(settings.db_settings.PLATFORM_CORE_DB) as db:
        cost_per_unit = await get_service_pricing(db, service_id)
        if cost_per_unit is None:
            logger.warning(
                "No pricing found for service_id=%s — skipping billing for tenant=%s",
                service_id, tenant_id,
            )
            return

        cost = calculate_cost(total_tokens, cost_per_unit)

        if cost == 0:
            logger.warning(
                "Zero cost calculated for service_id=%s (no pricing configured) — skipping",
                service_id,
            )
            return

        await deduct_balance(db, tenant_id, cost)
        # TODO: Update redis here.
        await db.commit()

        logger.info(
            "Billing applied | tenant=%s service=%s tokens=%d cost=%s",
            tenant_id, service_id, total_tokens, cost,
        )
