"""
SQLAlchemy ORM models for platform-core-service.

All tables live in the `ai4iplatform_core` database and share the single
`Base` declared here. The sub-packages (`model_management/`, `alert_management/`,
`pii_management/`, `pay_per_use/`) exist for organisation only — Alembic
autogenerate picks up everything that imports `Base`.

Import order:
  - Model first (FK dependency for Service).
  - Alert tables next — AlertDefinition before AlertAnnotation (FK), then
    NotificationReceiver before RoutingRule (FK), then AlertHistory (no FKs).
  - PII tables last (no FKs into other domains).
  - Pay-per-use tables last (Tier before TierQuota/TenantTierAssignment FK).
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Model-management tables
from app.models.model_management.model import Model  # noqa: E402
from app.models.model_management.service import Service  # noqa: E402

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

# PII-management tables (pii_ prefix, no cross-domain FKs)
from app.models.pii_management.audit_log import AuditLog  # noqa: E402
from app.models.pii_management.domain_policy import DomainPolicy  # noqa: E402
from app.models.pii_management.pattern import GeoLibrary, PatternLibrary  # noqa: E402
from app.models.pii_management.tenant_map import TenantPiiDomainMap  # noqa: E402

# Pay-per-use tables (Tier before TierQuota/TenantTierAssignment FK)
from app.models.pay_per_use.tier import Tier, TierQuota  # noqa: E402
from app.models.pay_per_use.tenant_tier_assignment import TenantTierAssignment  # noqa: E402
from app.models.pay_per_use.quota_usage import QuotaUsage  # noqa: E402
from app.models.pay_per_use.budget_usage import BudgetUsage  # noqa: E402

__all__ = [
    "Base",
    # model-management
    "Model",
    "Service",
    # alert-management
    "AlertAnnotation",
    "AlertDefinition",
    "AlertHistory",
    "NotificationReceiver",
    "RoutingRule",
    # pii-management
    "AuditLog",
    "DomainPolicy",
    "PatternLibrary",
    "GeoLibrary",
    "TenantPiiDomainMap",
    # pay-per-use
    "Tier",
    "TierQuota",
    "TenantTierAssignment",
    "QuotaUsage",
    "BudgetUsage",
]
