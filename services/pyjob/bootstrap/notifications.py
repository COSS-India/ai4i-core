"""Notification pipeline (ai4i_core.kafka) for jobs that send notifications.

Only daily_usage_consolidation's key expiry step uses it, so it is set up by
that step, not by the launcher; the other jobs need no Kafka settings:

    async with notifications():
        await emit_state_bulk(...)

Settings, ledger and failure log live in the platform-core DB; recipients
are read from the auth DB, with their emails decrypted by PII_ENCRYPTION_KEY.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from ai4i_core import pii_crypto
from ai4i_core.kafka import (
    Producer,
    close_kafka_producer,
    configure_notifications,
    init_kafka_producer,
    start_notifications,
    stop_notifications,
)
from ai4i_core.logging import get_logger

from bootstrap.config import get_settings
from bootstrap.database import auth_session_factory, platform_core_session_factory
from bootstrap.redis_client import get_redis

logger = get_logger(__name__)


@asynccontextmanager
async def notifications() -> AsyncIterator[None]:
    """Configure and start the pipeline, then flush Kafka and stop it on exit.
    Raises when a setting it needs is unset."""
    settings = get_settings()
    missing = [
        name
        for name in ("KAFKA_SERVER", "NOTIFICATION_TIMEZONE", "PII_ENCRYPTION_KEY")
        if not getattr(settings, name)
    ]
    if missing:
        raise RuntimeError(f"Notifications need {', '.join(missing)}")

    pii_crypto.configure_key(settings.PII_ENCRYPTION_KEY.get_secret_value())
    pii_crypto.validate_key()
    init_kafka_producer(bootstrap_servers=settings.KAFKA_SERVER, topic=settings.TOPIC_NOTIFICATION)
    configure_notifications(
        producer=Producer.PYJOB,
        core_session_factory=platform_core_session_factory(),
        auth_session_factory=auth_session_factory(),
        redis=get_redis(),
        decrypt_email=pii_crypto.decrypt_email,
        topic=settings.TOPIC_NOTIFICATION,
    )
    await start_notifications()
    logger.info("Notification pipeline started | topic=%s", settings.TOPIC_NOTIFICATION)
    try:
        yield
    finally:
        await stop_notifications()
        close_kafka_producer()
