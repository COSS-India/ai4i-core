from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import DeletedIdData, MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.policy_management.fields import NAME_MAX_LEN, clean_name


class PolicyTypeItem(BaseModel):
    """One row of the policy_type table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    policy_type: str
    policy_fields: Dict[str, Any]


class PolicyTypeListData(BaseModel):
    items: List[PolicyTypeItem]


class PolicyTypeCreate(BaseModel):
    """policy_type name is required and must be unique; policy_fields defaults
    to an empty object if omitted."""

    policy_type: str = Field(..., max_length=NAME_MAX_LEN)
    policy_fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("policy_type", mode="before")
    @classmethod
    def validate_policy_type(cls, v):
        return clean_name(v, "Policy Type")


class PolicyTypeUpdate(BaseModel):
    """All fields optional — only supplied keys are changed."""

    policy_type: Optional[str] = Field(None, max_length=NAME_MAX_LEN)
    policy_fields: Optional[Dict[str, Any]] = None

    @field_validator("policy_type", mode="before")
    @classmethod
    def validate_policy_type(cls, v):
        if v is None:
            return v
        return clean_name(v, "Policy Type")


# ── Route response envelopes ──


class ListPolicyTypeResponse(SuccessResponse):
    """GET /policies/policy-types"""

    data: PolicyTypeListData


class GetPolicyTypeResponse(SuccessResponse):
    """GET /policies/policy-types/{policy_type_id}"""

    data: PolicyTypeItem


class CreatePolicyTypeResponse(BaseModel):
    """POST /policies/policy-types"""

    success: bool
    id: int
    message: str


class UpdatePolicyTypeResponse(SuccessResponseWithMeta):
    """PUT /policies/policy-types/{policy_type_id}"""

    data: PolicyTypeItem
    meta: MessageMeta


class DeletePolicyTypeResponse(SuccessResponseWithMeta):
    """DELETE /policies/policy-types/{policy_type_id}"""

    data: DeletedIdData
    meta: MessageMeta
