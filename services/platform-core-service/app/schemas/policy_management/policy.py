from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.policy_management.policy import GuardrailScope
from app.schemas.common import DeletedIdData, MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.policy_management.fields import (
    DESCRIPTION_MAX_LEN,
    NAME_MAX_LEN,
    clean_description,
    clean_name,
)

_EXAMPLE_POLICY_ITEM = {
    "id": 1,
    "policy_id": "PID-0001",
    "name": "PII Redaction Policy",
    "description": "Redacts personally identifiable information from LLM outputs.",
    "domain": ["healthcare", "finance"],
    "guardrail_scope": "output",
    "is_global": False,
    "sub_category_id": 1,
    "is_active": True,
    "policy_type_id": [1, 2],
    "created_at": "2026-10-09T10:00:00Z",
    "updated_at": "2026-10-09T10:00:00Z",
    "created_by": "user-uuid-123",
    "updated_by": None,
}


class PolicyCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "PII Redaction Policy",
                "description": "Redacts personally identifiable information from LLM outputs.",
                "domain": ["healthcare", "finance"],
                "guardrail_scope": "output",
                "is_global": False,
                "sub_category_id": 1,
                "policy_type_id": [1, 2],
            }
        }
    )

    name: str = Field(..., max_length=NAME_MAX_LEN, description="Unique policy name (case-insensitive).")
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX_LEN, description="Optional description.")
    domain: List[str] = Field(..., min_length=1, description="One or more domains this policy applies to.")
    guardrail_scope: GuardrailScope = Field(..., description="Enforcement side: input, output, or both.")
    is_global: bool = Field(False, description="Whether this policy applies globally across all tenants.")
    sub_category_id: int = Field(..., gt=0, le=2_147_483_647, description="Sub-category this policy belongs to.")
    policy_type_id: List[int] = Field(..., min_length=1, description="One or more policy type IDs.")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        return clean_name(v, "Policy")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v):
        return clean_description(v)

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain(cls, v):
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("domain must contain at least one entry")
        return v

    @field_validator("policy_type_id", mode="before")
    @classmethod
    def validate_policy_type_id(cls, v):
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("policy_type_id must contain at least one entry")
        return v


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "description": "Updated description.",
                "domain": ["healthcare"],
                "guardrail_scope": "both",
                "is_global": True,
                "is_active": True,
                "sub_category_id": 1,
                "policy_type_id": [1, 2],
            }
        }
    )

    id: int = Field(..., gt=0, le=2_147_483_647, description="Integer primary key of the policy to update.")
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX_LEN, description="Updated description.")
    domain: Optional[List[str]] = Field(None, description="Replacement domain list (≥1 entry if supplied).")
    guardrail_scope: Optional[GuardrailScope] = Field(None, description="New guardrail scope.")
    is_global: Optional[bool] = Field(None, description="Update global flag.")
    is_active: Optional[bool] = Field(None, description="Activate or deactivate the policy.")
    sub_category_id: Optional[int] = Field(None, gt=0, le=2_147_483_647, description="New sub-category ID.")
    policy_type_id: Optional[List[int]] = Field(None, description="Replacement policy type list (≥1 entry if supplied).")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v):
        return clean_description(v)

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain(cls, v):
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("domain must contain at least one entry")
        return v

    @field_validator("policy_type_id", mode="before")
    @classmethod
    def validate_policy_type_id(cls, v):
        if isinstance(v, list) and len(v) == 0:
            raise ValueError("policy_type_id must contain at least one entry")
        return v


class PolicyItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"example": _EXAMPLE_POLICY_ITEM},
    )

    id: int = Field(..., description="Auto-incremented integer primary key.")
    policy_id: str = Field(..., description="Auto-generated human-readable ID, e.g. SPP-0001.")
    name: str = Field(..., description="Unique policy name.")
    description: Optional[str] = Field(None, description="Optional description.")
    domain: List[str] = Field(..., description="Domains this policy applies to.")
    guardrail_scope: GuardrailScope = Field(..., description="Enforcement side: input, output, or both.")
    is_global: bool = Field(..., description="Whether this policy is global.")
    sub_category_id: int = Field(..., description="Parent sub-category ID.")
    is_active: bool = Field(..., description="Whether this policy is currently active.")
    policy_type_id: Optional[List[int]] = Field(None, description="Associated policy type IDs.")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp.")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp.")
    created_by: Optional[str] = Field(None, description="User ID who created this policy.")
    updated_by: Optional[str] = Field(None, description="User ID who last updated this policy.")


class CreatedPolicyData(BaseModel):
    policy_id: str = Field(..., description="Auto-generated policy ID, e.g. PID-0001.")


class PolicyListData(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"items": [_EXAMPLE_POLICY_ITEM]}}
    )

    items: List[PolicyItem]


# ── Route response envelopes ──


class ListPolicyResponse(SuccessResponse):
    """GET /policies"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": {"items": [_EXAMPLE_POLICY_ITEM]},
            }
        }
    )

    data: PolicyListData


class GetPolicyResponse(SuccessResponse):
    """GET /policies/{id}"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": _EXAMPLE_POLICY_ITEM,
            }
        }
    )

    data: PolicyItem


class CreatePolicyResponse(SuccessResponseWithMeta):
    """POST /policies"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": {"policy_id": "PID-0001"},
                "meta": {"message": "Policy 'PII Redaction Policy' created successfully."},
            }
        }
    )

    data: CreatedPolicyData
    meta: MessageMeta


class UpdatePolicyResponse(SuccessResponseWithMeta):
    """PUT /policies"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": _EXAMPLE_POLICY_ITEM,
                "meta": {"message": "Policy 'PII Redaction Policy' updated."},
            }
        }
    )

    data: PolicyItem
    meta: MessageMeta


class DeletePolicyResponse(SuccessResponseWithMeta):
    """DELETE /policies/{id}"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": {"id": 1},
                "meta": {"message": "Policy 1 deleted."},
            }
        }
    )

    data: DeletedIdData
    meta: MessageMeta
