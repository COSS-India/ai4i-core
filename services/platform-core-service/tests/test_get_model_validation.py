"""Unit tests: GET /models/{model_id} rejects structurally invalid model_id
with 422 before any DB lookup is attempted (AI4IDS-1932).

Regression: previously any string reached ModelService.get_model() unvalidated,
so a malformed model_id fell all the way through to EntityNotFoundError (404)
instead of being rejected at the request boundary.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ValidationError

# conftest.py's ai4i_core.exceptions stub covers the exception classes but not
# success_response/error_response (app.core.responses needs both) — add them
# additively so this is the only test file affected.
import ai4i_core.exceptions as _ai4i_exc  # noqa: E402

if not hasattr(_ai4i_exc, "success_response"):
    _ai4i_exc.success_response = lambda data=None, meta=None: {"success": True, "data": data, **({"meta": meta} if meta else {})}
if not hasattr(_ai4i_exc, "error_response"):
    _ai4i_exc.error_response = lambda code, message, details=None: {"success": False, "error": {"code": code, "message": message}}

# app.dependencies.services pulls in the full alert-management repository
# layer just to build get_model_service's DI wiring — irrelevant here since
# every test below passes its own mock `svc` directly. Stub it out rather
# than dragging that whole chain in just to satisfy model.py's module-level
# `from app.dependencies.services import ModelService, get_model_service`.
if "app.dependencies.services" not in sys.modules:
    _deps_stub = types.ModuleType("app.dependencies.services")
    _deps_stub.ModelService = MagicMock
    _deps_stub.get_model_service = MagicMock()
    sys.modules["app.dependencies.services"] = _deps_stub

# app/routes/__init__.py eagerly imports every route module (alert, service,
# pii, ...) plus ai4i_core.bootstrap.versioning, none of which this suite's
# conftest stubs out. Load model.py directly by file path instead, bypassing
# the package __init__ so this test only pulls in what get_model_by_id
# actually needs.
_spec = importlib.util.spec_from_file_location(
    "app.routes.model", "app/routes/model.py"
)
_model_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.model"] = _model_route_mod
_spec.loader.exec_module(_model_route_mod)

_validate_model_id = _model_route_mod._validate_model_id
get_model_by_id = _model_route_mod.get_model_by_id


class TestValidateModelId:
    def test_accepts_hex_hash_id(self) -> None:
        """generate_model_id() output shape: 32-char lowercase hex."""
        assert _validate_model_id("a1b2c3d4e5f678901234567890abcdef") == "a1b2c3d4e5f678901234567890abcdef"

    def test_accepts_uuid_shape(self) -> None:
        """ModelService.get_model()'s UUID fallback path must keep working."""
        assert _validate_model_id("550e8400-e29b-41d4-a716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"

    def test_accepts_slash_and_underscore(self) -> None:
        assert _validate_model_id("org/team_model-1") == "org/team_model-1"

    def test_rejects_special_characters(self) -> None:
        """Exact repro string from the Jira ticket."""
        with pytest.raises(ValidationError, match="model_id must contain only"):
            _validate_model_id("not-a-valid-model-id!!")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValidationError, match="model_id must not be empty"):
            _validate_model_id("")

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(ValidationError, match="model_id must not be empty"):
            _validate_model_id("   ")

    def test_rejects_overlong_id(self) -> None:
        with pytest.raises(ValidationError, match="must not exceed"):
            _validate_model_id("a" * 256)

    def test_rejects_separator_only_string(self) -> None:
        """"---" is built entirely from allowed characters but has no
        alphanumeric content — the lookahead in _MODEL_ID_RE exists
        specifically to catch this, not just the character-class check."""
        with pytest.raises(ValidationError, match="model_id must contain only"):
            _validate_model_id("---")


class TestGetModelByIdRoute:
    @pytest.mark.asyncio
    async def test_invalid_model_id_raises_before_db_lookup(self) -> None:
        svc = MagicMock()
        svc.get_model = AsyncMock()

        with pytest.raises(ValidationError):
            await get_model_by_id("not-a-valid-model-id!!", version=None, svc=svc)

        svc.get_model.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_valid_model_id_proceeds_to_service(self) -> None:
        svc = MagicMock()
        svc.get_model = AsyncMock(return_value={"modelId": "abc123"})

        await get_model_by_id("abc123", version=None, svc=svc)

        svc.get_model.assert_awaited_once_with("abc123", version=None)
