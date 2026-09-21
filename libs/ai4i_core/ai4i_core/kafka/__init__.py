"""
ai4i_core.kafka — generic Kafka event-producer lifecycle for ALL microservices.

No service-specific imports here; callers pass their own bootstrap
servers/topic/enabled flag into init_kafka_producer().
"""

from .producer import (
    init_kafka_producer,
    close_kafka_producer,
    publish_event,
    publish_admin_event,
    get_kafka_producer_client,
)
from .notification_settings_cache import (
    refresh_all as refresh_notification_settings_cache,
    invalidate as invalidate_notification_settings_cache,
    is_notification_enabled,
    get_threshold_bands,
    get_notification_id,
    get_channels,
    start_listener as start_notification_settings_listener,
    stop_listener as stop_notification_settings_listener,
    configure as _configure_notification_settings_cache_redis,
    CHANNEL as NOTIFICATION_SETTINGS_CHANNEL,
)
from .ledger import (
    check_and_record_threshold,
    check_and_record_exhaustion,
    check_and_record_action,
    check_and_record_actions_bulk,
)
from .ledger_cache import configure as _configure_ledger_cache_redis
from .notification_names import NotificationName, NotificationType, NotificationChannel
from .delivery_status import DeliveryStatus


def configure_notification_cache_redis(redis_client) -> None:
    """Hand notification_settings_cache and ledger_cache the Redis client to
    read/write through — call this once at service startup, before
    refresh_notification_settings_cache()/any notification check, with
    whichever Redis client the service has already initialized. Both caches
    need this explicitly: not every service uses ai4i_core.bootstrap's own
    Redis singleton (auth-service and platform-core-service each run their
    own local one instead)."""
    _configure_notification_settings_cache_redis(redis_client)
    _configure_ledger_cache_redis(redis_client)

__all__ = [
    "init_kafka_producer",
    "close_kafka_producer",
    "publish_event",
    "publish_admin_event",
    "get_kafka_producer_client",
    "refresh_notification_settings_cache",
    "invalidate_notification_settings_cache",
    "is_notification_enabled",
    "get_threshold_bands",
    "get_notification_id",
    "get_channels",
    "start_notification_settings_listener",
    "stop_notification_settings_listener",
    "configure_notification_cache_redis",
    "NOTIFICATION_SETTINGS_CHANNEL",
    "check_and_record_threshold",
    "check_and_record_exhaustion",
    "check_and_record_action",
    "check_and_record_actions_bulk",
    "NotificationName",
    "NotificationType",
    "NotificationChannel",
    "DeliveryStatus",
]
