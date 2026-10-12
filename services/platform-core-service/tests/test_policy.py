"""app/schemas/policy_management/policy.py — PolicyCreate / PolicyUpdate validation.
app/routes/policy.py — /policies CRUD.

Two regressions covered:

1. Non-string domain entries (e.g. [5] or [None]) used to pass clean_name
   unchanged, then hit len(entry) and raise TypeError — which Pydantic v2 does
   NOT convert to a 422, so callers received a 500 instead.  The fix raises
   ValueError inside clean_name, which Pydantic catches and turns into a 422.
   TestPolicyCreateSchemaDomain and TestPolicyUpdateSchemaDomain assert this.

2. ?offset=99999999999999999999 overflowed asyncpg's int64 and caused a 500.
   The Query le= bound now rejects it as 422 at the HTTP layer.
   TestListPoliciesOffsetBound verifies this via FastAPI's TestClient, which
   exercises the full ASGI validation stack without reaching the handler.

The route module is loaded by file path for the same reason
test_policy_category.py does: app/routes/__init__.py eagerly imports
ai4i_core.bootstrap.versioning, which conftest does not stub.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import DuplicateEntityError, InsufficientPermissionsError
from app.schemas.policy_management.policy import PolicyCreate, PolicyUpdate

_spec = importlib.util.spec_from_file_location("app.routes.policy", "app/routes/policy.py")
_policy_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.policy"] = _policy_routes
_spec.loader.exec_module(_policy_routes)

# Minimal ASGI app used only for HTTP-layer (Query constraint) tests.
# The handler is never reached in those tests, so no DB dependency is needed.
_app = FastAPI()
_app.include_router(_policy_routes.router)
_client = TestClient(_app, raise_server_exceptions=False)

_VALID_CREATE = dict(
    name="PII Redaction",
    domain=["healthcare"],
    guardrail_scope="output",
    is_global=False,
    sub_category_id=1,
    policy_type_id=[1],
)


def _request(*, is_admin: bool = True) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": "1"} if is_admin else {"X-Permission-IDS": "5"}
    return request


# ── PolicyCreate domain validation ───────────────────────────────────────────


class TestPolicyCreateSchemaDomain:
    @pytest.mark.parametrize("bad_entry", [5, None, {"k": "v"}, True])
    def test_non_string_domain_entry_raises_validation_error(self, bad_entry):
        """Before the fix these raised TypeError inside len(entry) → 500.
        After the fix clean_name raises ValueError → Pydantic turns it into 422."""
        with pytest.raises(PydanticValidationError, match="must be a string"):
            PolicyCreate(**{**_VALID_CREATE, "domain": [bad_entry]})

    def test_mixed_list_with_non_string_entry_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="must be a string"):
            PolicyCreate(**{**_VALID_CREATE, "domain": ["healthcare", 5]})

    def test_empty_domain_list_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="at least one entry"):
            PolicyCreate(**{**_VALID_CREATE, "domain": []})

    @pytest.mark.parametrize("blank", ["", "   ", "​"])
    def test_blank_domain_entry_is_rejected(self, blank):
        with pytest.raises(PydanticValidationError, match="is required"):
            PolicyCreate(**{**_VALID_CREATE, "domain": [blank]})

    def test_domain_entry_longer_than_100_chars_is_rejected(self):
        with pytest.raises(PydanticValidationError):
            PolicyCreate(**{**_VALID_CREATE, "domain": ["x" * 101]})

    def test_domain_entries_are_trimmed(self):
        obj = PolicyCreate(**{**_VALID_CREATE, "domain": ["  healthcare  ", " finance "]})
        assert obj.domain == ["healthcare", "finance"]

    def test_valid_domain_passes(self):
        obj = PolicyCreate(**_VALID_CREATE)
        assert obj.domain == ["healthcare"]


# ── PolicyUpdate domain validation ───────────────────────────────────────────


class TestPolicyUpdateSchemaDomain:
    _BASE = dict(id=1)

    @pytest.mark.parametrize("bad_entry", [5, None, {"k": "v"}, True])
    def test_non_string_domain_entry_raises_validation_error(self, bad_entry):
        """Same clean_name guard as PolicyCreate — both validators share the fix."""
        with pytest.raises(PydanticValidationError, match="must be a string"):
            PolicyUpdate(**{**self._BASE, "domain": [bad_entry]})

    def test_mixed_list_with_non_string_entry_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="must be a string"):
            PolicyUpdate(**{**self._BASE, "domain": ["finance", None]})

    def test_empty_domain_list_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="at least one entry"):
            PolicyUpdate(**{**self._BASE, "domain": []})

    def test_domain_entries_are_trimmed(self):
        obj = PolicyUpdate(**{**self._BASE, "domain": ["  healthcare  "]})
        assert obj.domain == ["healthcare"]

    def test_none_domain_is_allowed(self):
        obj = PolicyUpdate(**self._BASE)
        assert obj.domain is None


# ── Offset Query-parameter bound ─────────────────────────────────────────────


class TestListPoliciesOffsetBound:
    """Query-parameter bounds are enforced by FastAPI's ASGI validation layer
    before the handler runs, so no DB or service mock is required for 422 cases."""

    def test_offset_overflow_returns_422(self):
        resp = _client.get("/policies", params={"offset": "99999999999999999999"})
        assert resp.status_code == 422

    def test_negative_offset_returns_422(self):
        resp = _client.get("/policies", params={"offset": "-1"})
        assert resp.status_code == 422


# ── list_policies route ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestListPoliciesRoute:
    async def test_wraps_items_in_envelope(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.policy_service, "list_policies", AsyncMock(return_value=([], 0))
        )
        resp = await _policy_routes.list_policies(
            request=_request(),
            response=MagicMock(),
            name=None,
            sub_category_id=None,
            offset=0,
            limit=100,
            session=MagicMock(),
        )
        assert resp.success is True
        assert resp.meta.total == 0
        assert resp.meta.offset == 0
        assert resp.meta.limit == 100

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock(return_value=([], 0))
        monkeypatch.setattr(_policy_routes.policy_service, "list_policies", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.list_policies(
                request=_request(is_admin=False),
                response=MagicMock(),
                name=None,
                sub_category_id=None,
                offset=0,
                limit=100,
                session=MagicMock(),
            )
        stub.assert_not_awaited()


# ── create_policy route ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCreatePolicyRoute:
    async def test_returns_policy_id_and_message(self, monkeypatch):
        created = MagicMock()
        created.policy_id = "PID-0001"
        created.name = "PII Redaction"
        monkeypatch.setattr(
            _policy_routes.policy_service, "create_policy", AsyncMock(return_value=created)
        )
        resp = await _policy_routes.create_policy(
            payload=PolicyCreate(**_VALID_CREATE),
            request=_request(),
            session=MagicMock(),
        )
        assert resp.data.policy_id == "PID-0001"
        assert "PII Redaction" in resp.meta.message

    async def test_duplicate_propagates(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.policy_service, "create_policy",
            AsyncMock(side_effect=DuplicateEntityError("Policy 'PII Redaction'")),
        )
        with pytest.raises(DuplicateEntityError):
            await _policy_routes.create_policy(
                payload=PolicyCreate(**_VALID_CREATE),
                request=_request(),
                session=MagicMock(),
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_policy_routes.policy_service, "create_policy", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.create_policy(
                payload=PolicyCreate(**_VALID_CREATE),
                request=_request(is_admin=False),
                session=MagicMock(),
            )
        stub.assert_not_awaited()
