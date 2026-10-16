"""app/schemas/policy_management/policy_type.py — PolicyTypeCreate validation.
app/routes/policy.py — /policies/policy-types CRUD.

Covers the clean_name guard tightening: passing a non-string as policy_type
now raises an explicit ValidationError instead of returning the raw value to
Pydantic. The observable result (ValidationError) was already the same for
scalar str fields via Pydantic's own type check, but the fix makes the error
message explicit ("must be a string") and consistent with the domain-list fix.

Route tests cover permission guards, happy-path envelopes, and error propagation
for list, create, get, and delete policy-type endpoints.

The route module is loaded by file path for the same reason
test_policy_category.py does: app/routes/__init__.py eagerly imports
ai4i_core.bootstrap.versioning, which conftest does not stub.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import EntityNotFoundError, InsufficientPermissionsError
from app.schemas.policy_management.policy_type import PolicyTypeCreate, PolicyTypeItem, PolicyTypeUpdate

_spec = importlib.util.spec_from_file_location("app.routes.policy", "app/routes/policy.py")
_policy_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.policy"] = _policy_routes
_spec.loader.exec_module(_policy_routes)


def _request(*, is_admin: bool = True) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": "1"} if is_admin else {"X-Permission-IDS": "5"}
    return request


def _pt_item(id=1, policy_type="PII Redaction") -> PolicyTypeItem:
    return PolicyTypeItem(id=id, policy_type=policy_type, policy_fields={})


class TestPolicyTypeCreateSchema:
    def test_policy_type_is_required(self):
        with pytest.raises(PydanticValidationError):
            PolicyTypeCreate()

    @pytest.mark.parametrize("name", ["", "   ", "​"])
    def test_blank_name_is_rejected(self, name):
        with pytest.raises(PydanticValidationError, match="Policy Type Name is required"):
            PolicyTypeCreate(policy_type=name)

    @pytest.mark.parametrize("value", [5, None, ["healthcare"], {"k": "v"}])
    def test_non_string_name_raises_validation_error(self, value):
        with pytest.raises(PydanticValidationError, match="Policy Type Name must be a string"):
            PolicyTypeCreate(policy_type=value)

    def test_name_is_trimmed(self):
        assert PolicyTypeCreate(policy_type="  Safety  ").policy_type == "Safety"

    def test_name_longer_than_100_chars_is_rejected(self):
        with pytest.raises(PydanticValidationError):
            PolicyTypeCreate(policy_type="x" * 101)

    def test_padding_does_not_count_toward_max_length(self):
        obj = PolicyTypeCreate(policy_type="  " + "x" * 100 + "  ")
        assert obj.policy_type == "x" * 100

    def test_policy_fields_defaults_to_empty_dict(self):
        assert PolicyTypeCreate(policy_type="Safety").policy_fields == {}

    @pytest.mark.parametrize("policy_fields", [
        {"Finance": {"custom_field": []}},          # old domain-keyed shape
        {"custom_fields": []},                      # typo
        {"custom_field": [], "description": "x"},
    ])
    def test_unknown_policy_fields_keys_are_rejected(self, policy_fields):
        with pytest.raises(PydanticValidationError, match="unknown keys"):
            PolicyTypeCreate(policy_type="Safety", policy_fields=policy_fields)

    def test_unknown_policy_fields_keys_are_rejected_on_update(self):
        with pytest.raises(PydanticValidationError, match="unknown keys"):
            PolicyTypeUpdate(policy_type_id=1, policy_fields={"Finance": {}})

    @pytest.mark.parametrize("entity", [
        {"entity_name": 5}, {"entity_name": ""}, {"entity_name": "   "}, {"name": "PERSON"}, "PERSON",
    ])
    def test_model_supported_field_entity_needs_string_name(self, entity):
        with pytest.raises(PydanticValidationError, match="model_supported_field"):
            PolicyTypeCreate(
                policy_type="Safety",
                policy_fields={"model_supported_field": [{"en": [entity]}]},
            )

    @pytest.mark.parametrize("raw", [" PERSON ", "PERSON\u200b", "\tPERSON"])
    def test_model_supported_field_entity_name_is_stored_cleaned(self, raw):
        obj = PolicyTypeCreate(
            policy_type="Safety",
            policy_fields={"model_supported_field": [{"en": [{"entity_name": raw}]}]},
        )
        assert obj.policy_fields["model_supported_field"][0]["en"][0]["entity_name"] == "PERSON"

    def test_custom_field_entity_name_is_stored_cleaned(self):
        obj = PolicyTypeCreate(
            policy_type="Safety",
            policy_fields={"custom_field": [
                {"entity_name": " MED_ID\u200b", "examples": ["a", "b", "c"], "regex": "\\d+"}]},
        )
        assert obj.policy_fields["custom_field"][0]["entity_name"] == "MED_ID"

    def test_entity_names_are_stored_cleaned_on_update(self):
        obj = PolicyTypeUpdate(
            policy_type_id=1,
            policy_fields={"model_supported_field": [{"en": [{"entity_name": " PERSON "}]}]},
        )
        assert obj.policy_fields["model_supported_field"][0]["en"][0]["entity_name"] == "PERSON"

    def test_flat_shape_with_null_fields_is_accepted(self):
        obj = PolicyTypeCreate(
            policy_type="Safety",
            policy_fields={"custom_field": None, "model_supported_field": None},
        )
        assert obj.policy_fields == {"custom_field": None, "model_supported_field": None}

    def test_custom_field_entry_requires_at_least_3_examples(self):
        with pytest.raises(PydanticValidationError, match="3 examples"):
            PolicyTypeCreate(
                policy_type="Medical PII",
                policy_fields={
                    "custom_field": [
                        {"entity_name": "MED_ID", "examples": ["a", "b"], "regex": "\\d+"}
                    ]
                },
            )

    def test_custom_field_blank_example_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="non-blank string"):
            PolicyTypeCreate(
                policy_type="Medical PII",
                policy_fields={
                    "custom_field": [
                        {"entity_name": "MED_ID", "examples": ["", "", ""], "regex": "\\d+"}
                    ]
                },
            )

    def test_custom_field_non_string_example_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="non-blank string"):
            PolicyTypeCreate(
                policy_type="Medical PII",
                policy_fields={
                    "custom_field": [
                        {"entity_name": "MED_ID", "examples": [1, 2, 3], "regex": "\\d+"}
                    ]
                },
            )

    def test_custom_field_entry_requires_regex(self):
        with pytest.raises(PydanticValidationError, match="regex"):
            PolicyTypeCreate(
                policy_type="Medical PII",
                policy_fields={
                    "custom_field": [
                        {"entity_name": "MED_ID", "examples": ["a", "b", "c"], "regex": ""}
                    ]
                },
            )

    def test_custom_field_non_string_regex_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="regex"):
            PolicyTypeCreate(
                policy_type="Medical PII",
                policy_fields={
                    "custom_field": [
                        {"entity_name": "MED_ID", "examples": ["a", "b", "c"], "regex": 123}
                    ]
                },
            )

    @pytest.mark.parametrize("bad_name", [5, None, ["list"], {"k": "v"}])
    def test_custom_field_non_string_entity_name_is_rejected(self, bad_name):
        with pytest.raises(PydanticValidationError, match="must be a string"):
            PolicyTypeCreate(
                policy_type="Medical PII",
                policy_fields={
                    "custom_field": [
                        {"entity_name": bad_name, "examples": ["a", "b", "c"], "regex": "\\d+"}
                    ]
                },
            )

    @pytest.mark.parametrize("blank_name", ["", "   ", "​"])
    def test_custom_field_blank_entity_name_is_rejected(self, blank_name):
        with pytest.raises(PydanticValidationError, match="Entity Name is required"):
            PolicyTypeCreate(
                policy_type="Medical PII",
                policy_fields={
                    "custom_field": [
                        {"entity_name": blank_name, "examples": ["a", "b", "c"], "regex": "\\d+"}
                    ]
                },
            )

    def test_too_many_custom_field_entries_is_rejected(self):
        entries = [
            {"entity_name": f"FIELD_{i}", "examples": ["a", "b", "c"], "regex": "\\d+"}
            for i in range(101)
        ]
        with pytest.raises(PydanticValidationError, match="100"):
            PolicyTypeCreate(
                policy_type="PII",
                policy_fields={"custom_field": entries},
            )

    def test_exactly_max_custom_field_entries_is_accepted(self):
        entries = [
            {"entity_name": f"FIELD_{i}", "examples": ["a", "b", "c"], "regex": "\\d+"}
            for i in range(100)
        ]
        obj = PolicyTypeCreate(
            policy_type="PII",
            policy_fields={"custom_field": entries},
        )
        assert len(obj.policy_fields["custom_field"]) == 100

    def test_regex_exceeding_max_length_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="1000"):
            PolicyTypeCreate(
                policy_type="PII",
                policy_fields={
                    "custom_field": [
                        {"entity_name": "FIELD", "examples": ["a", "b", "c"], "regex": "a" * 1001}
                    ]
                },
            )

    def test_regex_at_max_length_is_accepted(self):
        obj = PolicyTypeCreate(
            policy_type="PII",
            policy_fields={
                "custom_field": [
                    {"entity_name": "FIELD", "examples": ["a", "b", "c"], "regex": "a" * 1000}
                ]
            },
        )
        assert obj.policy_type == "PII"

    def test_valid_payload_is_accepted(self):
        obj = PolicyTypeCreate(
            policy_type="Medical PII",
            policy_fields={
                "custom_field": [
                    {"entity_name": "MED_ID", "examples": ["a", "b", "c"], "regex": "MED-\\d+"}
                ]
            },
        )
        assert obj.policy_type == "Medical PII"


@pytest.mark.asyncio
class TestListPolicyTypesRoute:
    async def test_wraps_items_in_envelope(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.policy_type_service, "list_policy_types",
            AsyncMock(return_value=[_pt_item()]),
        )
        resp = await _policy_routes.list_policy_types(request=_request(), session=MagicMock())
        assert resp.success is True
        assert [i.policy_type for i in resp.data.items] == ["PII Redaction"]

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_policy_routes.policy_type_service, "list_policy_types", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.list_policy_types(request=_request(is_admin=False), session=MagicMock())
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestCreatePolicyTypeRoute:
    async def test_returns_id_and_message(self, monkeypatch):
        created = MagicMock()
        created.id = 4
        created.policy_type = "Finance PII"
        monkeypatch.setattr(
            _policy_routes.policy_type_service, "create_policy_type", AsyncMock(return_value=created)
        )
        resp = await _policy_routes.create_policy_type(
            payload=PolicyTypeCreate(policy_type="Finance PII"),
            request=_request(),
            session=MagicMock(),
        )
        assert resp.data.id == 4
        assert "Finance PII" in resp.meta.message

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_policy_routes.policy_type_service, "create_policy_type", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.create_policy_type(
                payload=PolicyTypeCreate(policy_type="Finance PII"),
                request=_request(is_admin=False),
                session=MagicMock(),
            )
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestGetPolicyTypeRoute:
    async def test_returns_item(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.policy_type_service, "get_policy_type",
            AsyncMock(return_value=_pt_item(id=5, policy_type="Finance PII")),
        )
        resp = await _policy_routes.get_policy_type(
            request=_request(), policy_type_id=5, session=MagicMock()
        )
        assert resp.data.id == 5
        assert resp.data.policy_type == "Finance PII"

    async def test_not_found_propagates(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.policy_type_service, "get_policy_type",
            AsyncMock(side_effect=EntityNotFoundError("Policy type 5")),
        )
        with pytest.raises(EntityNotFoundError):
            await _policy_routes.get_policy_type(
                request=_request(), policy_type_id=5, session=MagicMock()
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_policy_routes.policy_type_service, "get_policy_type", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.get_policy_type(
                request=_request(is_admin=False), policy_type_id=5, session=MagicMock()
            )
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestDeletePolicyTypeRoute:
    async def test_returns_deleted_id_and_message(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.policy_type_service, "delete_policy_type", AsyncMock(return_value=7)
        )
        resp = await _policy_routes.delete_policy_type(
            request=_request(), policy_type_id=7, session=MagicMock()
        )
        assert resp.data.id == 7
        assert "7" in resp.meta.message

    async def test_not_found_propagates(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.policy_type_service, "delete_policy_type",
            AsyncMock(side_effect=EntityNotFoundError("Policy type 7")),
        )
        with pytest.raises(EntityNotFoundError):
            await _policy_routes.delete_policy_type(
                request=_request(), policy_type_id=7, session=MagicMock()
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_policy_routes.policy_type_service, "delete_policy_type", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.delete_policy_type(
                request=_request(is_admin=False), policy_type_id=7, session=MagicMock()
            )
        stub.assert_not_awaited()
