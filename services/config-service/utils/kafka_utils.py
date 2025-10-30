import json
import logging
from typing import Any, Dict, Optional

from aiokafka import AIOKafkaProducer


logger = logging.getLogger(__name__)


async def _publish(producer: Optional[AIOKafkaProducer], topic: str, payload: Dict[str, Any]) -> None:
    if not producer:
        return
    try:
        await producer.send_and_wait(topic, json.dumps(payload).encode("utf-8"))
    except Exception as e:
        logger.warning(f"Kafka publish failed: {e}")


async def publish_config_event(producer: Optional[AIOKafkaProducer], topic: str, payload: Dict[str, Any]) -> None:
    await _publish(producer, topic, payload)


async def publish_feature_flag_event(producer: Optional[AIOKafkaProducer], topic: str, payload: Dict[str, Any]) -> None:
    await _publish(producer, topic, payload)


async def publish_service_registry_event(producer: Optional[AIOKafkaProducer], topic: str, payload: Dict[str, Any]) -> None:
    await _publish(producer, topic, payload)


