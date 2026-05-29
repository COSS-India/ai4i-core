"""Alert-management enums (severity, category, urgency, rbac_role).

These are the canonical sets used by the alert feature. Request/response
schemas currently keep `str` typing with case-insensitive validators (to
preserve the wire contract of the old alert-management-service); the enums
below are the source of truth for valid values.
"""

from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Category(str, Enum):
    APPLICATION = "application"
    INFRASTRUCTURE = "infrastructure"


class Urgency(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RbacRole(str, Enum):
    """RBAC role used to resolve email recipients on a notification receiver."""

    ADMIN = "ADMIN"
    MODERATOR = "MODERATOR"
    USER = "USER"
    GUEST = "GUEST"


VALID_SEVERITIES = {member.value for member in Severity}
VALID_CATEGORIES = {member.value for member in Category}
VALID_URGENCIES = {member.value for member in Urgency}
VALID_RBAC_ROLES = {member.value for member in RbacRole}
