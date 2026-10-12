from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import DeletedIdData, MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.policy_management.fields import NAME_MAX_LEN, clean_name


def _validate_custom_fields(policy_fields: Dict[str, Any]) -> Dict[str, Any]:
    """If policy_fields contains a 'custom_field' list, every entry must have
    at least 3 examples and a non-empty regex."""
    custom_field_entries = policy_fields.get("custom_field")
    if not custom_field_entries:
        return policy_fields

    if not isinstance(custom_field_entries, list):
        raise ValueError("'custom_field' must be a list of objects.")

    for entry in custom_field_entries:
        if not isinstance(entry, dict):
            raise ValueError("Each item inside 'custom_field' must be an object.")

        entity_name = entry.get("entity_name", "<unknown>")

        examples = entry.get("examples")
        if not examples or not isinstance(examples, list) or len(examples) < 3:
            raise ValueError(
                f"custom_field entry '{entity_name}': at least 3 examples are required."
            )

        regex = entry.get("regex")
        if not regex or not str(regex).strip():
            raise ValueError(
                f"custom_field entry '{entity_name}': 'regex' is required."
            )

    return policy_fields


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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "policy_type": "Medical Policy PII",
                "policy_fields": {
                    "model_supported_field": [
                        {
                            "en": [
                                {"entity_name": "MEDICAL_ID"},
                                {"entity_name": "EMAIL_ADDRESS"},
                            ],
                            "hi": [
                                {"entity_name": "EDUCATION_ID"},
                            ],
                        }
                    ],
                    "custom_field": [
                        {
                            "entity_name": "MEDICAL_ID",
                            "examples": ["MED001", "MED002", "MED003"],
                            "regex": "MED-\\d{6}",
                        },
                        {
                            "entity_name": "EMPLOYEE_NUM",
                            "examples": ["ED001", "ED002", "ED003"],
                            "regex": "EMP\\d{4}",
                        },
                    ],
                },
            }
        }
    )

    policy_type: str = Field(..., max_length=NAME_MAX_LEN)
    policy_fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("policy_type", mode="before")
    @classmethod
    def validate_policy_type(cls, v):
        return clean_name(v, "Policy Type")

    @model_validator(mode="after")
    def validate_custom_fields(self):
        _validate_custom_fields(self.policy_fields)
        return self


class PolicyTypeUpdate(BaseModel):
    """All fields optional — only supplied keys are changed."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "policy_type_id": 2,
                "policy_fields": {
                    "model_supported_field": [
                        {
                            "en": [
                                {"entity_name": "MEDICAL_ID"},
                                {"entity_name": "EMAIL_ADDRESS"},
                            ],
                            "hi": [
                                {"entity_name": "EDUCATION_ID"},
                            ],
                        }
                    ],
                    "custom_field": [
                        {
                            "entity_name": "MEDICAL_ID",
                            "examples": ["MED001", "MED002", "MED003"],
                            "regex": "MED-\\d{6}",
                        },
                        {
                            "entity_name": "EMPLOYEE_NUM",
                            "examples": ["ED001", "ED002", "ED003"],
                            "regex": "EMP\\d{4}",
                        },
                    ],
                },
            }
        }
    )

    policy_type_id: int = Field(..., gt=0, le=2_147_483_647)
    policy_fields: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_custom_fields(self):
        if self.policy_fields is not None:
            _validate_custom_fields(self.policy_fields)
        return self


# ── Route response envelopes ──


class ListPolicyTypeResponse(SuccessResponse):
    """GET /policies/policy-types"""

    data: PolicyTypeListData


class GetPolicyTypeResponse(SuccessResponse):
    """GET /policies/policy-types/{policy_type_id}"""

    data: PolicyTypeItem


class CreatePolicyTypeResponse(SuccessResponseWithMeta):
    """POST /policies/policy-types"""

    data: DeletedIdData
    meta: MessageMeta


class UpdatePolicyTypeResponse(SuccessResponseWithMeta):
    """PUT /policies/policy-types/{policy_type_id}"""

    data: PolicyTypeItem
    meta: MessageMeta


class DeletePolicyTypeResponse(SuccessResponseWithMeta):
    """DELETE /policies/policy-types/{policy_type_id}"""

    data: DeletedIdData
    meta: MessageMeta
