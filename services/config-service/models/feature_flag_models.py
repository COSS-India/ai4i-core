"""
Pydantic models for feature flag API requests and responses
"""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class FeatureFlagEvaluationRequest(BaseModel):
    """Request model for feature flag evaluation"""
    flag_name: str = Field(..., description="Feature flag identifier", min_length=1)
    user_id: Optional[str] = Field(None, description="User identifier for targeting")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context attributes")
    default_value: Union[bool, str, int, float, dict] = Field(..., description="Fallback value if flag evaluation fails")
    environment: str = Field(..., description="Environment name (development|staging|production)")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError("environment must be one of development, staging, production")
        return v


class BulkEvaluationRequest(BaseModel):
    """Request model for bulk feature flag evaluation"""
    flag_names: List[str] = Field(..., description="List of flag names to evaluate", min_length=1)
    user_id: Optional[str] = Field(None, description="User identifier for targeting")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context attributes")
    environment: str = Field(..., description="Environment name (development|staging|production)")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError("environment must be one of development, staging, production")
        return v


class FeatureFlagCreate(BaseModel):
    """Request model for creating a feature flag"""
    name: str = Field(..., description="Flag name", min_length=1, max_length=255)
    description: Optional[str] = Field(None, description="Flag description")
    is_enabled: bool = Field(False, description="Whether the flag is enabled")
    environment: str = Field(..., description="Environment name (development|staging|production)")
    rollout_percentage: Optional[str] = Field(None, description="Rollout percentage as string")
    target_users: Optional[List[str]] = Field(None, description="List of target user IDs")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError("environment must be one of development, staging, production")
        return v


class FeatureFlagEvaluationResponse(BaseModel):
    """Response model for feature flag evaluation"""
    flag_name: str
    value: Union[bool, str, int, float, dict]
    variant: Optional[str] = None
    reason: str = Field(..., description="Evaluation reason (TARGETING_MATCH, DEFAULT, ERROR)")
    evaluated_at: str


class FeatureFlagResponse(BaseModel):
    """Response model for feature flag details"""
    id: int
    name: str
    description: Optional[str]
    is_enabled: bool
    environment: str
    rollout_percentage: Optional[str]
    target_users: Optional[List[str]]
    unleash_flag_name: Optional[str]
    last_synced_at: Optional[str]
    evaluation_count: int
    last_evaluated_at: Optional[str]
    created_at: str
    updated_at: str


class FeatureFlagListResponse(BaseModel):
    """Response model for feature flag list"""
    items: List[FeatureFlagResponse]
    total: int
    limit: int
    offset: int

