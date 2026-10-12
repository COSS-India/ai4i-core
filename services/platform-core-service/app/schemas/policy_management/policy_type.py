from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import DeletedIdData, MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.policy_management.fields import NAME_MAX_LEN, clean_name


def _validate_custom_fields(policy_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Each top-level key in policy_fields is a domain (e.g. Education, Finance).
    Every domain must have a 'custom_field' list where each entry has a mandatory
    entity_name, at least 3 examples, and a non-empty regex."""
    for domain, domain_value in policy_fields.items():
        if not isinstance(domain_value, dict):
            raise ValueError(f"policy_fields['{domain}'] must be an object.")

        custom_field_entries = domain_value.get("custom_field")
        if not custom_field_entries:
            continue

        if not isinstance(custom_field_entries, list):
            raise ValueError(f"policy_fields['{domain}']['custom_field'] must be a list.")

        for entry in custom_field_entries:
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Each item in policy_fields['{domain}']['custom_field'] must be an object."
                )

            entity_name = entry.get("entity_name")
            if not entity_name or not str(entity_name).strip():
                raise ValueError(
                    f"policy_fields['{domain}'] custom_field entry: "
                    "'entity_name' is required and must not be blank."
                )

            examples = entry.get("examples")
            if not examples or not isinstance(examples, list) or len(examples) < 3:
                raise ValueError(
                    f"policy_fields['{domain}'] custom_field entry '{entity_name}': "
                    "at least 3 examples are required."
                )

            regex = entry.get("regex")
            if not regex or not str(regex).strip():
                raise ValueError(
                    f"policy_fields['{domain}'] custom_field entry '{entity_name}': "
                    "'regex' is required."
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
                    "Education": {
                        "custom_field": [
                            {
                                "entity_name": "STUDENT_NAME",
                                "examples": ["Arjun Kumar", "Priya Sharma", "Ravi Verma"],
                                "regex": "\\b[A-Z][a-z]+(?:\\s[A-Z][a-z]+){1,3}\\b",
                            },
                            {
                                "entity_name": "STUDENT_ID",
                                "examples": ["EDU20231234", "STU2024567", "SCH12345"],
                                "regex": "\\b[A-Z]{2,5}\\d{4,10}\\b",
                            },
                            {
                                "entity_name": "EMAIL_ADDRESS",
                                "examples": ["arjun@college.edu", "student@university.ac.in", "user@school.org"],
                                "regex": "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b",
                            },
                        ]
                    },
                    "Finance": {
                        "custom_field": [
                            {
                                "entity_name": "BANK_ACCOUNT_NUMBER",
                                "examples": ["123456789012", "987654321098", "112233445566"],
                                "regex": "\\b\\d{9,18}\\b",
                            },
                            {
                                "entity_name": "PAN_NUMBER",
                                "examples": ["ABCDE1234F", "PQRST5678G", "XYZWV9012H"],
                                "regex": "\\b[A-Z]{5}\\d{4}[A-Z]\\b",
                            },
                            {
                                "entity_name": "IFSC_CODE",
                                "examples": ["SBIN0000456", "HDFC0001234", "ICIC0005678"],
                                "regex": "\\b[A-Z]{4}0[A-Z0-9]{6}\\b",
                            },
                        ]
                    },
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
                "policy_type_id": 1,
                "policy_fields": {
                    "Healthcare": {
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
                        ]
                    },
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
