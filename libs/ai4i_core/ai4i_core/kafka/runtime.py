"""Process-wide wiring of the notification pipeline.

Each producer service calls configure() once at startup (after its DB
engines, Redis client and Kafka producer exist), then start() to run the
invalidation listener, and stop() at shutdown.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional, Set

from . import constants as c
from .cache import TieredCache
from .config import NotificationSettings
from .constants import Producer
from .failure_log import FailureLogger
from .invalidation import InvalidationListener, origin_of
from .publisher import Publisher
from .recipients import DecryptEmail, RecipientResolver

logger = logging.getLogger(__name__)


@dataclass
class NotificationRuntime:
    config: NotificationSettings
    producer: Producer
    origin: str
    core_session_factory: Callable
    auth_session_factory: Callable
    redis: Any
    cache: TieredCache
    failures: FailureLogger
    recipients: RecipientResolver
    publisher: Publisher
    listener: InvalidationListener


_runtime: Optional[NotificationRuntime] = None
_background: Set[asyncio.Task] = set()


def configure(
    *,
    producer: Producer,
    core_session_factory: Callable,
    auth_session_factory: Callable,
    redis,
    decrypt_email: Optional[DecryptEmail] = None,
    config: Optional[NotificationSettings] = None,
    pod_name: Optional[str] = None,
    topic: str = c.NOTIFICATION_TOPIC,
) -> NotificationRuntime:
    """core_session_factory / auth_session_factory: async_sessionmaker (or
    any callable returning an async-context session) for ai4iplatform_core
    and ai4iplatform_auth. decrypt_email defaults to ai4i_core.pii_crypto."""
    global _runtime
    if decrypt_email is None:
        from ai4i_core.pii_crypto import decrypt_email as decrypt_email  # noqa: PLW0127
    config = config or NotificationSettings()
    pod_name = pod_name or os.getenv("POD_NAME") or os.getenv("HOSTNAME")
    producer = Producer(producer)
    origin = origin_of(producer.value, pod_name)
    failures = FailureLogger(core_session_factory, producer, pod_name, config.notif_failure_throttle_s)
    cache = TieredCache(
        redis=redis, session_factory=core_session_factory, config=config, failure_log=failures, origin=origin
    )
    listener = InvalidationListener(redis, origin, cache.apply_invalidation, cache.drop_all)
    _runtime = NotificationRuntime(
        config=config,
        producer=producer,
        origin=origin,
        core_session_factory=core_session_factory,
        auth_session_factory=auth_session_factory,
        redis=redis,
        cache=cache,
        failures=failures,
        recipients=RecipientResolver(decrypt_email),
        publisher=Publisher(topic, failures),
        listener=listener,
    )
    return _runtime


def is_configured() -> bool:
    """False when this process never configured the pipeline (for example,
    its platform-core DB is not set up); callers then skip notifications."""
    return _runtime is not None


def get_runtime() -> NotificationRuntime:
    if _runtime is None:
        raise RuntimeError("Notification pipeline is not configured; call ai4i_core.kafka.configure_notifications()")
    return _runtime


async def start() -> None:
    get_runtime().listener.start()


async def stop() -> None:
    if _runtime is not None:
        await _runtime.listener.stop()
    if _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


def run_in_background(coroutine: Coroutine) -> asyncio.Task:
    """Run a notification step after the business request, without making it
    wait: a notification problem never fails or slows the request."""
    task = asyncio.create_task(coroutine)
    _background.add(task)

    def _done(finished: asyncio.Task) -> None:
        _background.discard(finished)
        if not finished.cancelled() and finished.exception() is not None:
            logger.error("Notification step failed", exc_info=finished.exception())

    task.add_done_callback(_done)
    return task
