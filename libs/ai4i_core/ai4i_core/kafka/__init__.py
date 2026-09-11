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
    CHANNEL as NOTIFICATION_SETTINGS_CHANNEL,
)
from .ledger import (
    check_and_record_threshold,
    check_and_record_exhaustion,
    check_and_record_action,
)

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
    "NOTIFICATION_SETTINGS_CHANNEL",
    "check_and_record_threshold",
    "check_and_record_exhaustion",
    "check_and_record_action",
]
