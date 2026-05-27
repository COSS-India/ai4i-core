"""
SQLAlchemy ORM models for platform-core-service.

Tables are placed in the public schema (models, services).
Import order: Model first (FK dependency for Service).
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

from app.models.model import Model  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.models.pay_per_use.usage_record import UsageRecord  # noqa: E402
from app.models.pay_per_use.wallet import WalletBalance, WalletTransaction  # noqa: E402
from app.models.pay_per_use.quota_usage import QuotaUsage  # noqa: E402
from app.models.pay_per_use.quota_config import QuotaConfig, QuotaServiceLimit  # noqa: E402
from app.models.pay_per_use.rate_limit_config import RateLimitConfig  # noqa: E402
from app.models.pay_per_use.subscription_plan import SubscriptionPlan  # noqa: E402

__all__ = [
    "Base",
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
]
