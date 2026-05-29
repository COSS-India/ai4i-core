"""
SQLAlchemy ORM models for platform-core-service.

All tables live in the `ai4iplatform_core` database and share the single
`Base` declared here. The sub-packages (`model_management/`, `alert_management/`)
exist for organisation only — Alembic autogenerate picks up everything that
imports `Base`.

Import order:
  - Model first (FK dependency for Service).
  - Alert tables next — AlertDefinition before AlertAnnotation (FK), then
    NotificationReceiver before RoutingRule (FK), then AlertHistory (no FKs).
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Model-management tables
from app.models.model_management.model import Model  # noqa: E402
from app.models.model_management.service import Service  # noqa: E402
from app.models.pay_per_use.usage_record import UsageRecord  # noqa: E402
from app.models.pay_per_use.wallet import WalletBalance, WalletTransaction  # noqa: E402
from app.models.pay_per_use.quota_usage import QuotaUsage  # noqa: E402
from app.models.pay_per_use.quota_config import QuotaConfig, QuotaServiceLimit  # noqa: E402
from app.models.pay_per_use.rate_limit_config import RateLimitConfig  # noqa: E402
from app.models.pay_per_use.subscription_plan import SubscriptionPlan  # noqa: E402

# Alert-management tables (FK-ordered)
from app.models.alert_management.alert_definition import (  # noqa: E402
    AlertAnnotation,
    AlertDefinition,
)
from app.models.alert_management.notification_receiver import (  # noqa: E402
    NotificationReceiver,
)
from app.models.alert_management.routing_rule import RoutingRule  # noqa: E402
from app.models.alert_management.alert_history import AlertHistory  # noqa: E402

__all__ = [
    "Base",
    # model-management
    "Model",
    "Service",
    "UsageRecord",
    "WalletBalance",
    "WalletTransaction",
    "QuotaUsage",
    "QuotaConfig",
    "QuotaServiceLimit",
    "RateLimitConfig",
    "SubscriptionPlan",
    # alert-management
    "AlertAnnotation",
    "AlertDefinition",
    "AlertHistory",
    "NotificationReceiver",
    "RoutingRule",
]
