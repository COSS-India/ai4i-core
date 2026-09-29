"""Environment settings of the notification pipeline.

Every field reads the environment variable of the same name, upper-cased
(NOTIF_L1_SETTINGS_TTL_S, NOTIF_MONITOR_COOLDOWN_S, ...), from the process
environment or the service's .env file. A service can also
build it from its own settings object and pass it to runtime.configure().
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from . import constants as c


class NotificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    # L1 in-memory cache
    notif_l1_settings_ttl_s: int = c.DEFAULT_L1_SETTINGS_TTL_S
    notif_l1_sub_ttl_s: int = c.DEFAULT_L1_SUB_TTL_S
    notif_l1_ledger_ttl_s: int = c.DEFAULT_L1_LEDGER_TTL_S
    notif_l1_sub_max: int = c.DEFAULT_L1_SUB_MAX
    notif_l1_ledger_max: int = c.DEFAULT_L1_LEDGER_MAX

    # L2 Redis
    notif_redis_settings_ttl_s: int = c.DEFAULT_REDIS_SETTINGS_TTL_S
    notif_redis_sub_ttl_s: int = c.DEFAULT_REDIS_SUB_TTL_S
    notif_redis_ledger_ttl_s: int = c.DEFAULT_REDIS_LEDGER_TTL_S

    # Failure log
    notif_failure_throttle_s: int = c.DEFAULT_FAILURE_THROTTLE_S
    notif_failure_retention_days: int = c.DEFAULT_FAILURE_RETENTION_DAYS

    # BAND rule: a triggered monitoring row re-arms only after this cooldown
    notif_monitor_cooldown_s: int = c.DEFAULT_MONITOR_COOLDOWN_S
