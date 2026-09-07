"""Regression test for the /auth/validate API-key path's format check.

`APIKeyService.validate_api_key()` returns `{"valid": False, "message": ...}`
(rather than raising `InvalidAPIKeyError`) when the token isn't even
hex-key shaped. `_validate_api_key`'s `try/except InvalidAPIKeyError` around
that call never catches this case, so without an explicit `valid` check the
result fell through the rest of the function as if it were a real key: no
`user_id` in the dict meant `X-User-ID` was silently never set, and the
route still returned `ValidateAPIKeyResponse(valid=True, ...)` with a 200 —
surfacing as a confusing "missing X-User-ID" failure downstream instead of a
clear 401.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response

from app.routes.validation import _validate_api_key


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.headers = {}  # no X-Original-Method/URI -> endpoint check passes through
    return request


@pytest.mark.asyncio
class TestValidateApiKeyInvalidFormat:
    async def test_malformed_key_returns_401_not_valid_true(self):
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "valid": False,
            "message": "Invalid API key format.",
        }
        response = Response()

        result = await _validate_api_key("not-a-hex-key", _mock_request(), response, api_key_svc)

        assert result.status_code == 401
        assert b"INVALID_API_KEY_FORMAT" in result.body
        assert b"Invalid API key format." in result.body
        assert "X-User-ID" not in response.headers

    async def test_valid_key_still_returns_valid_true(self):
        # Keys are owned by Applications, not Users (migration e9f0a1b2c3d4
        # dropped api_key.user_id in favor of application_id) — the
        # validate_api_key payload and the response headers it drives
        # reflect that: no X-User-ID for this branch, X-Application-ID
        # (and X-API-Key-ID) instead.
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42,
            "application_id": "7",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
        }
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True
        assert "X-User-ID" not in response.headers
        assert response.headers["X-Application-ID"] == "7"
        assert response.headers["X-API-Key-ID"] == "42"
