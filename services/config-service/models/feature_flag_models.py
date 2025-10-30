from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class FeatureFlagCreate(BaseModel):
    name: str = Field(..., description="Feature flag name", min_length=1, max_length=255)
    description: Optional[str] = Field(None, description="Description of the flag")
    is_enabled: bool = Field(False, description="Whether the flag is enabled")
    rollout_percentage: float = Field(0.0, description="Percentage rollout 0-100")
    target_users: Optional[List[str]] = Field(None, description="Specific user IDs to target")
    environment: str = Field(..., description="Environment for the flag")

    @field_validator("rollout_percentage")
    @classmethod
    def validate_rollout(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("rollout_percentage must be between 0 and 100")
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError("environment must be one of development, staging, production")
        return v


class FeatureFlagUpdate(BaseModel):
    is_enabled: Optional[bool] = Field(None, description="Enable/disable flag")
    rollout_percentage: Optional[float] = Field(None, description="Percentage rollout 0-100")
    target_users: Optional[List[str]] = Field(None, description="Specific user IDs to target")

    @field_validator("rollout_percentage")
    @classmethod
    def validate_rollout(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v < 0 or v > 100:
            raise ValueError("rollout_percentage must be between 0 and 100")
        return v


class FeatureFlagEvaluate(BaseModel):
    flag_name: str = Field(..., description="Flag to evaluate")
    user_id: str = Field(..., description="User ID for evaluation")
    environment: str = Field(..., description="Environment for evaluation")


class FeatureFlagResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_enabled: bool
    rollout_percentage: float
    target_users: Optional[List[str]]
    environment: str
    created_at: str
    updated_at: str


class FeatureFlagEvaluationResponse(BaseModel):
    enabled: bool
    reason: str


