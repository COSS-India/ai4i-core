from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# --- Policy Dimensions used by SMR ---
class LatencyPolicy(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostPolicy(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class AccuracyPolicy(str, Enum):
    SENSITIVE = "sensitive"
    STANDARD = "standard"


# --- Request & Response ---
class PolicyRequest(BaseModel):
    user_id: str = Field(..., description="User Identity")
    tenant_id: Optional[str] = Field(None, description="Organization ID")
    latency_policy: Optional[LatencyPolicy] = Field(
        None, description="Optional override for latency policy"
    )
    cost_policy: Optional[CostPolicy] = Field(
        None, description="Optional override for cost policy"
    )
    accuracy_policy: Optional[AccuracyPolicy] = Field(
        None, description="Optional override for accuracy policy"
    )


class PolicyResponse(BaseModel):
    """
    Minimal policy response for SMR:
    - policy_id/policy_version: for observability
    - latency/cost/accuracy: the only values SMR uses for routing decisions
    """

    policy_id: str
    policy_version: str = Field(..., example="v1.0")
    fallback_applied: bool = False

    # Actual policy values used for service matching (as strings for easier serialization)
    latency_policy: Optional[str] = Field(
        None, description="Actual latency policy value used"
    )
    cost_policy: Optional[str] = Field(
        None, description="Actual cost policy value used"
    )
    accuracy_policy: Optional[str] = Field(
        None, description="Actual accuracy policy value used"
    )