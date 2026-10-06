"""Shared constants for the notification and alert pipeline.

Single source of truth for every name, key and fixed value the producers
(auth-service, platform-core-service, payperuse_consumer, the monitoring
evaluator) use, so no call site re-types a raw string. Enum values match the
Postgres enums and CHECK constraints of the notification tables in
ai4iplatform_core.
"""

from enum import Enum


class NotificationName(str, Enum):
    """configs_notification_alert.name — notification_alert_name_enum."""

    TIER_ASSIGNED = "TIER_ASSIGNED"
    TIER_CHANGED = "TIER_CHANGED"
    BUDGET_ASSIGNED = "BUDGET_ASSIGNED"
    BUDGET_UPDATED = "BUDGET_UPDATED"
    QUOTA_LIMIT_UPDATED = "QUOTA_LIMIT_UPDATED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    QUOTA_THRESHOLD = "QUOTA_THRESHOLD"
    BUDGET_THRESHOLD = "BUDGET_THRESHOLD"
    ERROR_RATE_4XX = "ERROR_RATE_4XX"
    ERROR_RATE_5XX = "ERROR_RATE_5XX"
    LATENCY_P50 = "LATENCY_P50"
    LATENCY_P95 = "LATENCY_P95"
    LATENCY_P99 = "LATENCY_P99"


class NotificationType(str, Enum):
    """configs_notification_alert.type — notification_alert_type_enum."""

    NOTIFICATION = "NOTIFICATION"
    ALERT = "ALERT"
    MONITORING = "MONITORING"


class NotificationModule(str, Enum):
    """configs_notification_alert.module — notification_alert_module_enum."""

    TIER = "TIER"
    BUDGET = "BUDGET"
    QUOTA = "QUOTA"
    MONITORING = "MONITORING"


class NotificationChannel(str, Enum):
    """configs_notification_alert.channels — notification_alert_channel_enum."""

    EMAIL = "EMAIL"
    SMS = "SMS"
    SLACK = "SLACK"
    WHATSAPP = "WHATSAPP"


class NotificationScope(str, Enum):
    """configs_notification_alert.scope — notification_alert_scope_enum."""

    GLOBAL = "GLOBAL"
    INSTITUTION = "INSTITUTION"


class ThresholdUnit(str, Enum):
    """notification_alert_threshold.unit — notification_threshold_unit_enum."""

    PERCENT = "PERCENT"
    SECONDS = "SECONDS"


class Severity(str, Enum):
    """notification_alert_threshold.severity — notification_severity_enum."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class RecipientRole(str, Enum):
    """Keys of configs_notification_alert.recipient_roles, and roles.name."""

    ADMIN = "ADMIN"
    TENANT_ADMIN = "TENANT ADMIN"
    MODERATOR = "MODERATOR"


class DedupRule(str, Enum):
    """How a type decides whether an event is new. Fixed per type in code."""

    STATE = "STATE"
    BAND = "BAND"


class Decision(str, Enum):
    """Outcome of one evaluation. DUPLICATE: the claim lost to another caller."""

    FIRE = "FIRE"
    RESET = "RESET"
    SKIP = "SKIP"
    DUPLICATE = "DUPLICATE"


class FailureStage(str, Enum):
    """notification_alert_failure_log.stage — notification_failure_stage_enum."""

    VALIDATION = "VALIDATION"
    SETTINGS = "SETTINGS"
    SUBSCRIPTION = "SUBSCRIPTION"
    SOURCE = "SOURCE"
    LEDGER = "LEDGER"
    DETAILS = "DETAILS"
    RECIPIENTS = "RECIPIENTS"
    PUBLISH = "PUBLISH"
    CACHE = "CACHE"
    #: notifications_consumer: the event reached no recipient on any channel.
    DELIVERY = "DELIVERY"


class FailureCode(str, Enum):
    """notification_alert_failure_log.error_code."""

    UNKNOWN_NOTIFICATION = "UNKNOWN_NOTIFICATION"
    INVALID_SUBJECT = "INVALID_SUBJECT"
    SETTINGS_UNAVAILABLE = "SETTINGS_UNAVAILABLE"
    SUBSCRIPTION_UNAVAILABLE = "SUBSCRIPTION_UNAVAILABLE"
    TENANT_LOOKUP_FAILED = "TENANT_LOOKUP_FAILED"
    PROMETHEUS_UNREACHABLE = "PROMETHEUS_UNREACHABLE"
    PROMETHEUS_TIMEOUT = "PROMETHEUS_TIMEOUT"
    PROMETHEUS_BAD_RESPONSE = "PROMETHEUS_BAD_RESPONSE"
    LEDGER_READ_FAILED = "LEDGER_READ_FAILED"
    LEDGER_WRITE_FAILED = "LEDGER_WRITE_FAILED"
    DETAILS_PARTIAL = "DETAILS_PARTIAL"
    RECIPIENTS_LOOKUP_FAILED = "RECIPIENTS_LOOKUP_FAILED"
    NO_RECIPIENTS = "NO_RECIPIENTS"
    KAFKA_SEND_FAILED = "KAFKA_SEND_FAILED"
    CACHE_READ_FAILED = "CACHE_READ_FAILED"
    CACHE_WRITE_FAILED = "CACHE_WRITE_FAILED"
    INVALIDATION_PUBLISH_FAILED = "INVALIDATION_PUBLISH_FAILED"
    # notifications_consumer
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    NO_SUPPORTED_CHANNEL = "NO_SUPPORTED_CHANNEL"
    EMAIL_SEND_FAILED = "EMAIL_SEND_FAILED"


class Producer(str, Enum):
    """notification_alert_failure_log.producer — ck_failure_log_producer."""

    AUTH_SERVICE = "auth-service"
    PLATFORM_CORE_SERVICE = "platform-core-service"
    PAYPERUSE_CONSUMER = "payperuse-consumer"
    MONITORING_EVALUATOR = "monitoring-evaluator"
    NOTIFICATIONS_CONSUMER = "notifications-consumer"


class Operation(str, Enum):
    """error_detail.operation — the named step that failed."""

    SETTINGS_FILL = "settings_fill"
    SUBSCRIPTION_FILL = "subscription_fill"
    LEDGER_READ = "ledger_read"
    LEDGER_CLAIM_BAND = "ledger_claim_band"
    LEDGER_RESET = "ledger_reset"
    LEDGER_CLAIM_STATE = "ledger_claim_state"
    LEDGER_CLAIM_STATE_BULK = "ledger_claim_state_bulk"
    LEDGER_REREAD = "ledger_reread"
    DETAILS_LOOKUP = "details_lookup"
    TENANT_LOOKUP = "tenant_lookup"
    RECIPIENTS_LOOKUP = "recipients_lookup"
    KAFKA_SEND = "kafka_send"
    PROMETHEUS_QUERY = "prometheus_query"
    CACHE_READ = "cache_read"
    CACHE_WRITE = "cache_write"
    INVALIDATION_PUBLISH = "invalidation_publish"
    VALIDATE = "validate"
    EMAIL_SEND = "email_send"


class InvalidationKind(str, Enum):
    """kind of a message on the ntf:v1:invalidate channel."""

    SETTINGS = "SETTINGS"
    SUBSCRIPTION = "SUBSCRIPTION"
    LEDGER = "LEDGER"
    FLUSH = "FLUSH"


class SubjectKey(str, Enum):
    """Keys a ledger subject may carry."""

    MODEL_TASK_TYPE = "model_task_type"
    BILLING_MONTH = "billing_month"
    BUDGET_CEILING = "budget_ceiling"
    BUDGET_WINDOW = "budget_window"
    SERVICE_ID = "service_id"


class CacheName(str, Enum):
    """cache label of ntf_cache_requests_total."""

    SETTINGS = "settings"
    SUBSCRIPTION = "subscription"
    LEDGER = "ledger"


class CacheLayer(str, Enum):
    """layer label of ntf_cache_requests_total: L1 memory, L2 Redis, L3 DB."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class CacheResult(str, Enum):
    """result label of ntf_cache_requests_total."""

    HIT = "hit"
    MISS = "miss"
    ERROR = "error"


class PublishResult(str, Enum):
    """result label of ntf_publish_total."""

    SENT = "sent"
    FAILED = "failed"


# ── Fixed values ─────────────────────────────────────────────────────────────

#: tenant_id of every MONITORING ledger row and envelope.
PLATFORM_TENANT_ID = "PLATFORM"

#: Kafka topic the consumer reads.
NOTIFICATION_TOPIC = "notification.events"

ENVELOPE_SCHEMA_VERSION = 2
SETTINGS_SNAPSHOT_SCHEMA_VERSION = 1
INVALIDATION_MESSAGE_VERSION = 1

#: Role keys every recipient_roles object carries, per notification type.
MONITORING_RECIPIENT_ROLES = (RecipientRole.ADMIN, RecipientRole.MODERATOR)
TENANT_RECIPIENT_ROLES = (RecipientRole.ADMIN, RecipientRole.TENANT_ADMIN)

#: The two rows with a fixed, non-editable 100 % band.
EXHAUSTED_NAMES = frozenset({NotificationName.QUOTA_EXHAUSTED, NotificationName.BUDGET_EXHAUSTED})
EXHAUSTED_BAND_VALUE = 100

#: Subject formats.
BILLING_MONTH_FORMAT = "%Y-%m"
AMOUNT_DECIMALS = 2

#: error_detail.message and error_message are cut to this length.
ERROR_MESSAGE_MAX_CHARS = 2000

#: Quota ledger rows of billing months older than this are purged daily.
QUOTA_LEDGER_RETENTION_MONTHS = 3

# ── Redis ────────────────────────────────────────────────────────────────────

REDIS_KEY_PREFIX = "ntf:v1:"
SETTINGS_KEY = f"{REDIS_KEY_PREFIX}settings"  # K1
SUBSCRIPTION_KEY_PREFIX = f"{REDIS_KEY_PREFIX}sub:"  # K2
LEDGER_KEY_PREFIX = f"{REDIS_KEY_PREFIX}ledger:"  # K3
SETTINGS_FILL_LOCK_KEY = f"{REDIS_KEY_PREFIX}lock:settings-fill"  # K4
INVALIDATION_CHANNEL = f"{REDIS_KEY_PREFIX}invalidate"  # C1

#: subject_key of an empty subject.
EMPTY_SUBJECT_KEY = "_"

SETTINGS_FILL_LOCK_TTL_MS = 5000
SETTINGS_FILL_POLL_INTERVAL_S = 0.2
SETTINGS_FILL_POLL_ATTEMPTS = 5
SETTINGS_FILL_BACKOFF_S = 5

#: The last good settings snapshot is served, when Redis and the DB are both
#: down, for at most this long.
STALE_SETTINGS_MAX_AGE_S = 3600

LISTENER_RECONNECT_MIN_S = 1
LISTENER_RECONNECT_MAX_S = 30
#: Pub/Sub poll timeout; must stay below any Redis client socket_timeout.
LISTENER_POLL_TIMEOUT_S = 1.0

#: Deletes the lock only if the token still matches.
LOCK_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

# ── Configuration defaults (see config.NotificationSettings) ────────────────

DEFAULT_L1_SETTINGS_TTL_S = 60
DEFAULT_L1_SUB_TTL_S = 60
DEFAULT_L1_LEDGER_TTL_S = 30
DEFAULT_L1_SUB_MAX = 10000
DEFAULT_L1_LEDGER_MAX = 20000
DEFAULT_REDIS_SETTINGS_TTL_S = 600
DEFAULT_REDIS_SUB_TTL_S = 600
DEFAULT_REDIS_LEDGER_TTL_S = 900
DEFAULT_FAILURE_THROTTLE_S = 60
DEFAULT_MONITOR_COOLDOWN_S = 1800
DEFAULT_FAILURE_RETENTION_DAYS = 30
