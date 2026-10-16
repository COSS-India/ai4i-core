"""
SQLAlchemy ORM models for the policy management domain.

Category -> SubCategory -> Policy form the guardrail policy hierarchy;
PolicyType describes the configurable fields a policy can carry, and
PolicyAuditLog records which policies were applied to a request.

Postgres has no foreign keys on array elements, so Policy.policy_type_id
(-> policy_type.id) and PolicyAuditLog.policy_id (-> policy.id) are not
enforced by the database; the application layer must validate them.
"""

from app.models.policy_management.audit_log import PolicyAuditLog
from app.models.policy_management.category import Category
from app.models.policy_management.policy import GuardrailScope, Policy
from app.models.policy_management.policy_type import PolicyType
from app.models.policy_management.sub_category import SubCategory

__all__ = [
    "Category",
    "SubCategory",
    "PolicyType",
    "Policy",
    "GuardrailScope",
    "PolicyAuditLog",
]
