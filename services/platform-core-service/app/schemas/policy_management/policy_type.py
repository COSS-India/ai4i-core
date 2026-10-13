import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import DeletedIdData, MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.policy_management.fields import (
    MAX_CUSTOM_FIELDS,
    MAX_REGEX_LEN,
    NAME_MAX_LEN,
    clean_name,
)


def _validate_custom_fields(policy_fields: Dict[str, Any]) -> Dict[str, Any]:
    """policy_fields must be a flat object with a 'custom_field' list.
    Each entry must have entity_name, at least 3 non-blank string examples,
    and a non-blank compilable regex."""
    custom_field_entries = policy_fields.get("custom_field")
    if not custom_field_entries:
        return policy_fields

    if not isinstance(custom_field_entries, list):
        raise ValueError("policy_fields['custom_field'] must be a list.")

    if len(custom_field_entries) > MAX_CUSTOM_FIELDS:
        raise ValueError(
            f"policy_fields custom_field entries must not exceed {MAX_CUSTOM_FIELDS} "
            f"(got {len(custom_field_entries)})."
        )

    for entry in custom_field_entries:
        if not isinstance(entry, dict):
            raise ValueError("Each item in policy_fields['custom_field'] must be an object.")

        try:
            entity_name = clean_name(entry.get("entity_name"), "Entity")
        except ValueError as exc:
            raise ValueError(f"policy_fields custom_field entry: {exc}") from exc

        examples = entry.get("examples")
        if not examples or not isinstance(examples, list) or len(examples) < 3:
            raise ValueError(
                f"policy_fields custom_field entry '{entity_name}': "
                "at least 3 examples are required."
            )
        for i, ex in enumerate(examples):
            if not isinstance(ex, str) or not ex.strip():
                raise ValueError(
                    f"policy_fields custom_field entry '{entity_name}': "
                    f"examples[{i}] must be a non-blank string."
                )

        regex = entry.get("regex")
        if not isinstance(regex, str) or not regex.strip():
            raise ValueError(
                f"policy_fields custom_field entry '{entity_name}': "
                "'regex' must be a non-blank string."
            )
        if len(regex) > MAX_REGEX_LEN:
            raise ValueError(
                f"policy_fields custom_field entry '{entity_name}': "
                f"'regex' must not exceed {MAX_REGEX_LEN} characters (got {len(regex)})."
            )
        # Regex provided by the product team — compiled here to catch invalid patterns at validation time
        try:
            re.compile(regex)
        except re.error as exc:
            raise ValueError(
                f"policy_fields custom_field entry '{entity_name}': "
                f"invalid regex — {exc}."
            )

    model_supported_entries = policy_fields.get("model_supported_field")
    if model_supported_entries:
        if not isinstance(model_supported_entries, list):
            raise ValueError("policy_fields['model_supported_field'] must be a list.")
        for entry in model_supported_entries:
            if not isinstance(entry, dict):
                raise ValueError(
                    "Each item in policy_fields['model_supported_field'] must be an object."
                )
            for lang, entities in entry.items():
                if not isinstance(entities, list):
                    raise ValueError(
                        f"policy_fields['model_supported_field']['{lang}'] must be a list."
                    )
                for entity in entities:
                    if not isinstance(entity, dict) or not entity.get("entity_name"):
                        raise ValueError(
                            f"policy_fields['model_supported_field']['{lang}']: "
                            "each entry must have 'entity_name'."
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
                "policy_type": "PII",
                "policy_fields": {
                    "custom_field": [
                        {
                            "entity_name": "STUDENT_NAME",
                            "examples": ["Arjun Kumar", "Priya Sharma", "Ravi Verma"],
                            "regex": "\\b[A-Z][a-z]+(?:\\s[A-Z][a-z]+){1,3}\\b",
                        },
                        {
                            "entity_name": "BANK_ACCOUNT_NUMBER",
                            "examples": ["123456789012", "987654321098", "112233445566"],
                            "regex": "\\b\\d{9,18}\\b",
                        },
                        {
                            "entity_name": "AADHAAR_NUMBER",
                            "examples": ["1234 5678 9012", "9876 5432 1098", "1111 2222 3333"],
                            "regex": "\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b",
                        },
                    ],
                    "model_supported_field": [
                        {
                            "en": [
                                {"entity_name": "CREDIT_CARD_NUMBER"},
                                {"entity_name": "EMAIL_ADDRESS"},
                            ],
                            "hi": [
                                {"entity_name": "IN_PAN"},
                            ],
                        }
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
        self.policy_fields = _validate_custom_fields(self.policy_fields)
        return self


class PolicyTypeUpdate(BaseModel):
    """All fields optional — only supplied keys are changed."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "policy_type_id": 1,
                "policy_fields": {
                    "custom_field": [
                        {
                            "entity_name": "PATIENT_NAME",
                            "examples": ["Meena Raj", "Suresh Kumar", "Anita Singh"],
                            "regex": "\\b[A-Z][a-z]+(?:\\s[A-Z][a-z]+){1,3}\\b",
                        },
                        {
                            "entity_name": "AADHAAR_NUMBER",
                            "examples": ["1234 5678 9012", "9876 5432 1098", "1111 2222 3333"],
                            "regex": "\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b",
                        },
                        {
                            "entity_name": "HEALTH_INSURANCE_ID",
                            "examples": ["HIN9876543", "INS123456789", "POL987654321"],
                            "regex": "\\b[A-Z0-9]{6,20}\\b",
                        },
                    ],
                    "model_supported_field": [
                        {
                            "en": [
                                {"entity_name": "MEDICAL_ID"},
                                {"entity_name": "EMAIL_ADDRESS"},
                            ],
                            "hi": [
                                {"entity_name": "IN_AADHAAR"},
                            ],
                        }
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
            self.policy_fields = _validate_custom_fields(self.policy_fields)
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
