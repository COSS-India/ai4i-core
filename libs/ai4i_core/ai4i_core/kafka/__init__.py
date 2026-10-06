"""
ai4i_core.kafka — Kafka producer lifecycle and the shared notification
producer pipeline for every service.

No service-specific imports here; each service passes its own DB session
factories, Redis client and Kafka settings in at startup.
"""

from .producer import (
    init_kafka_producer,
    close_kafka_producer,
    get_kafka_producer_client,
)
from .constants import (
    NotificationName,
    NotificationType,
    NotificationModule,
    NotificationChannel,
    NotificationScope,
    ThresholdUnit,
    Severity,
    RecipientRole,
    DedupRule,
    Decision,
    FailureStage,
    FailureCode,
    Producer,
    Operation,
    InvalidationKind,
    SubjectKey,
    PLATFORM_TENANT_ID,
    NOTIFICATION_TOPIC,
)
from .config import NotificationSettings
from .specs import NotificationSpec, SPECS, get_spec
from .keys import (
    InvalidSubject,
    state_hash,
    subject_key,
    format_amount,
    billing_month_of,
    quota_subject,
    budget_subject,
    monitoring_subject,
    quota_limit_subject,
)
from .models import Band, Measurement, Recipient, SettingsRow, SettingsSnapshot, TenantSubscriptions
from .bands import band_for
from .ledger import purge_old_quota_rows, resettable_subjects
from .failure_log import producer_scope, purge_failures
from .runtime import (
    configure as configure_notifications,
    start as start_notifications,
    stop as stop_notifications,
    get_runtime as get_notification_runtime,
    is_configured as notifications_configured,
    run_in_background,
)
from .pipeline import (
    StateItem,
    BandItem,
    FireContext,
    emit_state,
    emit_state_bulk,
    emit_band_batch,
    names_that_can_fire,
    refresh_settings,
    refresh_subscriptions,
)

__all__ = [
    # Kafka producer lifecycle
    "init_kafka_producer",
    "close_kafka_producer",
    "get_kafka_producer_client",
    # constants
    "NotificationName",
    "NotificationType",
    "NotificationModule",
    "NotificationChannel",
    "NotificationScope",
    "ThresholdUnit",
    "Severity",
    "RecipientRole",
    "DedupRule",
    "Decision",
    "FailureStage",
    "FailureCode",
    "Producer",
    "Operation",
    "InvalidationKind",
    "SubjectKey",
    "PLATFORM_TENANT_ID",
    "NOTIFICATION_TOPIC",
    # configuration and type facts
    "NotificationSettings",
    "NotificationSpec",
    "SPECS",
    "get_spec",
    # subjects and fingerprints
    "InvalidSubject",
    "state_hash",
    "subject_key",
    "format_amount",
    "billing_month_of",
    "quota_subject",
    "budget_subject",
    "monitoring_subject",
    "quota_limit_subject",
    # values
    "Band",
    "Measurement",
    "Recipient",
    "SettingsRow",
    "SettingsSnapshot",
    "TenantSubscriptions",
    "band_for",
    # runtime
    "configure_notifications",
    "start_notifications",
    "stop_notifications",
    "get_notification_runtime",
    "notifications_configured",
    "run_in_background",
    # pipeline
    "StateItem",
    "BandItem",
    "FireContext",
    "emit_state",
    "emit_state_bulk",
    "emit_band_batch",
    "names_that_can_fire",
    "refresh_settings",
    "refresh_subscriptions",
    # maintenance (daily cleanup)
    "purge_old_quota_rows",
    "resettable_subjects",
    "producer_scope",
    "purge_failures",
]
