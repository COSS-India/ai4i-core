from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

# --- Policy Dimensions ---
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
    latency_policy: Optional[LatencyPolicy] = Field(None)
    cost_policy: Optional[CostPolicy] = Field(None)
    accuracy_policy: Optional[AccuracyPolicy] = Field(None)

class RoutingFlags(BaseModel):
    model_family: str
    model_variant: str
    priority: int
    routing_strategy: str
    max_cost_usd: float

class PolicyResponse(BaseModel):
    policy_id: str
    policy_version: str = Field(..., example="v1.0") # <--- ADDED THIS
    routing_flags: RoutingFlags
    fallback_applied: bool = False
