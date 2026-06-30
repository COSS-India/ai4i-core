"""
Async billing: fetch PPU pricing from Redis, calculate cost, emit to Kafka.

Designed to run as asyncio.create_task() after inference returns — the HTTP
response is already on the wire before this coroutine runs.  It never raises.

Redis key schema:
    ppu:svc:{service_id} → JSON {billing_unit_type, cost_per_unit, unit_size, unit_rate}

Cost formula:
    unit_rate set  → cost = units_consumed × unit_rate
    else           → cost = (units_consumed / unit_size) × cost_per_unit
"""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "ppu:svc:"


def _calculate_cost(pricing: dict, units_consumed: int) -> float:
    unit_rate = pricing.get("unit_rate")
    if unit_rate is not None:
        return units_consumed * float(unit_rate)
    cost_per_unit = float(pricing.get("cost_per_unit", 0))
    unit_size = max(float(pricing.get("unit_size", 1)), 1)
    return (units_consumed / unit_size) * cost_per_unit


async def compute_and_emit_billing(
    *,
    service_id: str,
    input_tokens: int,
    output_tokens: int,
    task_name: str = "",
    user_id: str = "",
    tenant_id: str = "",
    trace_id: str = "",
    span_id: str = "",
) -> None:
    """
    Fetch PPU pricing, compute cost, publish a billing event to Kafka.

    billing_unit_type controls which token count drives the cost:
        "input_tokens"  (default) → units_consumed = input_tokens
        "output_tokens"           → units_consumed = output_tokens
        "total_tokens"            → units_consumed = input_tokens + output_tokens

    The Kafka event is published to the same topic as OTel spans so downstream
    consumers (FluentBit → OpenSearch) can correlate via trace_id / span_id.
    """
    try:
        from ai4i_core.bootstrap.redis import get_redis_client
        from trace.setup import get_kafka_producer
        from config import settings

        logger.info("BILLING: started for service_id=%s input=%s output=%s", service_id, input_tokens, output_tokens)

        if not service_id:
            return

        try:
            redis = get_redis_client()
        except RuntimeError:
            logger.debug("Redis not initialized — billing skipped for service_id=%s", service_id)
            return

        raw = await redis.get(f"{_REDIS_KEY_PREFIX}{service_id}")
        if not raw:
            logger.debug("No PPU pricing found for service_id=%s", service_id)
            return

        pricing = json.loads(raw)
        billing_unit_type = pricing.get("billing_unit_type", "characters")

        if billing_unit_type == "tokens":
            # LLM-style: total tokens in + out
            units_consumed = input_tokens + output_tokens
        elif billing_unit_type == "minutes":
            # Audio services: input_tokens encodes 100 tokens/sec (see span_attributes._count_audio_tokens)
            # → divide by 6000 to get minutes, round up to at least 0.001
            units_consumed = max(round(input_tokens / 6000.0, 4), 0.001) if input_tokens else 0.001
        elif billing_unit_type == "characters":
            # Text services (NMT, TTS, NER, etc.): input_tokens = word count ≈ character proxy
            units_consumed = input_tokens
        else:
            units_consumed = input_tokens

        cost = _calculate_cost(pricing, units_consumed)

        billing_event = {
            "type": "billing",
            "context": {
                "trace_id": trace_id,
                "span_id": span_id,
            },
            "attributes": {
                "service_id": service_id,
                "task_name": task_name,
                "billing_unit_type": billing_unit_type,
                "units_consumed": units_consumed,
                "cost": float(f"{cost:.6f}"),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "userId": user_id,
                "tenantId": tenant_id,
            },
        }

        producer = get_kafka_producer()
        if producer is not None:
            topic = settings.KAFKA_TOPIC_OTEL_TRACE

            def _send():
                producer.send(topic, value=billing_event)
                producer.flush(timeout=5)

            await asyncio.get_event_loop().run_in_executor(None, _send)
        else:
            logger.info("billing_event: %s", json.dumps(billing_event, default=str))

    except Exception:
        logger.warning("Billing computation failed (non-critical)", exc_info=True)
