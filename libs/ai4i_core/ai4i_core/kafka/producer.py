"""
Generic Kafka event producer lifecycle and publish().

Used by ALL microservices. No service-specific imports — callers pass their
own bootstrap servers/topic/enabled flag in; this module holds no settings
object of its own.

Modeled on the one existing Kafka producer in this codebase,
services/inference-service/trace/setup.py's KafkaSpanExporter: a lazily-
imported, feature-flagged kafka-python KafkaProducer, JSON-serialized,
fire-and-forget send(). A missing/misconfigured broker must never break the
caller — every failure here is caught and logged, never raised.

publish_event() deliberately does NOT call flush() — unlike the exporter it's
modeled on, which calls flush() from OTel's own background BatchSpanProcessor
thread, publish_event() is called directly from request-handling / message-
handling async code. flush() blocks its caller until the broker acks (up to
its timeout), which would stall the event loop on every publish. Delivery
failures are caught via the returned future's errback, not via flush(); the
producer is only flushed at shutdown (close_kafka_producer), to drain
whatever is still buffered before the process exits.

send() itself is not purely non-blocking, though: kafka-python's send() can
block synchronously — in _wait_on_metadata and on buffer allocation — for up
to max_block_ms (5s here) whenever the broker is unreachable or metadata
isn't cached yet. Calling it straight from an async request handler would
stall that handler's whole event loop for up to 5s on a Kafka outage, not
just the one request. publish_event() offloads the actual send() call to
the default executor (run_in_executor) so it runs on a worker thread instead
of the loop thread; publish_event() itself returns immediately once the
work is scheduled, same fire-and-forget contract as before for the caller.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_producer: Optional[Any] = None
_default_topic: Optional[str] = None


def init_kafka_producer(bootstrap_servers: str, topic: str, enabled: bool = True) -> None:
    """Create the Kafka producer. Called during app/consumer startup.

    enabled=False (or init never called) leaves the module in a no-op state —
    publish() then silently drops events instead of raising, so a service that
    doesn't configure Kafka boots and runs exactly as before this existed.
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


def publish_event(
    event_name: str,
    tenant_id: str,
    subject: dict,
    details: dict,
    actor_id: str = "",
    topic: Optional[str] = None,
    occurred_at: Optional[str] = None,
) -> None:
    """Build the standard notification envelope and send it. Returns
    immediately from the caller's point of view — the actual send() call
    (which can block synchronously for up to max_block_ms on an unreachable
    broker) runs on a worker thread via run_in_executor, not the event loop
    thread; delivery itself then continues on the producer's own background
    sender thread as usual. Never raises: a synchronous failure (not
    initialized, serialization error) is caught here, an asynchronous
    delivery failure (broker unreachable, etc.) is caught via the errback
    and only logged.

    occurred_at: pass explicitly when the caller already computed it (e.g.
    to pass the identical timestamp into the ledger_notification_alert
    dedup check before deciding to publish at all). Defaults to now() when
    omitted."""
    if _producer is None:
        return
    envelope = {
        "event_name": event_name,
        "tenant_id": tenant_id,
        "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
        "actor_id": actor_id,
        "subject": subject,
        "details": details,
    }
    target_topic = topic or _default_topic
    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _send, target_topic, envelope, event_name)
    except RuntimeError:
        # No running loop (e.g. called from sync code, or at shutdown) —
        # fall back to sending inline; still bounded by max_block_ms, just
        # not offloaded off whatever thread called this.
        _send(target_topic, envelope, event_name)


def _send(topic: Optional[str], envelope: dict, event_name: str) -> None:
    """The actual blocking-capable send() call — always run off the event
    loop thread by publish_event() above. Never raises."""
    if _producer is None:
        return
    try:
        future = _producer.send(topic, value=envelope)
        future.add_errback(lambda exc: logger.warning("Failed to deliver event %s: %s", event_name, exc))
    except Exception as exc:
        logger.warning("Failed to publish event %s: %s", event_name, exc)


def publish_admin_event(
    event_name: str,
    tenant_id: str,
    subject: dict,
    details: dict,
    actor_id: str,
    topic: Optional[str] = None,
    occurred_at: Optional[str] = None,
) -> None:
    """Convenience wrapper over publish_event for the 5 "admin changed
    something" events (design doc §2.1/§9). occurred_at is the only
    timestamp in the envelope — pass it explicitly when the caller already
    precomputed it (e.g. to pass the identical timestamp into the
    ledger_notification_alert dedup check before deciding to publish at
    all), otherwise it defaults to now()."""
    publish_event(
        event_name=event_name,
        tenant_id=tenant_id,
        subject=subject,
        details=details,
        actor_id=actor_id,
        topic=topic,
        occurred_at=occurred_at,
    )


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
