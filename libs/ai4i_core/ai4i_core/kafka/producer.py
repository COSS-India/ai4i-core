"""
Kafka producer lifecycle, shared by every microservice.

A lazily imported, feature-flagged kafka-python KafkaProducer with a JSON
value serializer. Services call init_kafka_producer() at startup and
close_kafka_producer() at shutdown (which flushes what is still buffered).
The notification publisher (publisher.py) sends through
get_kafka_producer_client(); it never calls flush(), which would block its
caller until the broker acks.
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_producer: Optional[Any] = None
_default_topic: Optional[str] = None


def init_kafka_producer(bootstrap_servers: str, topic: str, enabled: bool = True) -> None:
    """Create the Kafka producer. Called during app/consumer startup.

    enabled=False (or init never called) leaves the module without a
    producer; get_kafka_producer_client() then raises, so a service that
    doesn't configure Kafka still boots.
    """
    global _producer, _default_topic
    _default_topic = topic
    if not enabled:
        logger.info("Kafka producer disabled.")
        return
    try:
        from kafka import KafkaProducer

        _producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            acks="all",
            retries=3,
            max_block_ms=5000,
        )
        logger.info("Kafka producer initialized: topic=%s servers=%s", topic, bootstrap_servers)
    except Exception as exc:
        logger.warning("Kafka producer init failed, events will not be published: %s", exc)
        _producer = None


def close_kafka_producer() -> None:
    """Flush and close the producer. Called during app/consumer shutdown."""
    global _producer
    if _producer is not None:
        try:
            _producer.flush(timeout=10)
            _producer.close()
        except Exception:
            pass
        _producer = None


def get_kafka_producer_client() -> Any:
    """Return the raw kafka-python KafkaProducer (for non-DI contexts)."""
    if _producer is None:
        raise RuntimeError("Kafka producer not initialized.")
    return _producer
