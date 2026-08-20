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
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "1",
            "permissions": [1, 2, 3],
        }
        response = Response()

        result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        assert result.valid is True
        assert response.headers["X-User-ID"] == "11111111-1111-1111-1111-111111111111"
