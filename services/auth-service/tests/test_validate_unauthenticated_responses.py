"""Regression coverage for /auth/validate's "cannot identify the caller"
contract (AI4IDS ticket: notification-alerts 401 leaking an API-key-flavored
error for a malformed bearer token).

Agreed contract (see validation.py's ``_unauthenticated`` docstring):

* 401 means the caller could not be identified at all — missing, malformed,
  unreadable, expired, or revoked token/API key. Every one of those cases
  now returns the exact same generic body ({"valid": false, "error":
  "UNAUTHENTICATED", "message": "Authentication failed."}) — never the
  specific reason (TOKEN_EXPIRED / TOKEN_INVALID / TOKEN_REVOKED /
  INVALID_API_KEY / INVALID_API_KEY_FORMAT), which used to leak which check
  failed (and, for a malformed bearer token specifically, wrongly implied
  this platform has an "API key" auth mode at all).
* 403 (INSUFFICIENT_PERMISSIONS, TIER_DEACTIVATED, BUDGET_EXPIRED) is a
  different case — the caller WAS identified, they're just not allowed to
  do this — and keeps its specific, actionable message. Not touched here;
  see test_validate_budget_expired.py and the tier/permission tests.
* The real reason is still logged server-side (for auth-service's own
  debugging/metrics), just never returned to the client.

This suite exercises every 401 branch in _validate_api_key/_validate_jwt
directly, so a future change that reintroduces a distinguishing error code
on any one of them fails loudly.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

from app.core.exceptions import InvalidAPIKeyError
from app.core.jwt_verifier import AuthClaims, JWTExpiredError, JWTVerificationError
from app.routes.validation import _validate_api_key, _validate_jwt

_GENERIC_BODY = b'"error":"UNAUTHENTICATED"'


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.headers = {}  # no X-Original-Method/URI -> endpoint check passes through
    return request


def _assert_generic_401(result, *forbidden_substrings: bytes) -> None:
    assert result.status_code == 401
    assert _GENERIC_BODY in result.body
    assert b"Authentication failed." in result.body
    for substring in forbidden_substrings:
        assert substring not in result.body, f"{substring!r} must not leak into the client response"


@pytest.mark.asyncio
class TestApiKeyPathIsGeneric:
    async def test_unknown_or_revoked_key_is_generic(self, caplog):
        """APIKeyService.validate_api_key raising InvalidAPIKeyError (key not
        found, or found but revoked/expired/ineligible) must not surface
        as INVALID_API_KEY to the client."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.side_effect = InvalidAPIKeyError()
        response = Response()

        with caplog.at_level(logging.INFO):
            result = await _validate_api_key("a" * 32, _mock_request(), response, api_key_svc)

        _assert_generic_401(result, b"INVALID_API_KEY", b"revoked")
        assert any("INVALID_API_KEY" in r.getMessage() for r in caplog.records), (
            "the real reason must still reach auth-service's own logs"
        )

    async def test_malformed_key_is_generic(self, caplog):
        """This is the exact bug report: a malformed/garbage bearer token
        falls through to the API-key path (it isn't a strict JWT), and used
        to come back as 401 INVALID_API_KEY_FORMAT — an "API key" branded
        error on a platform where the caller may never have meant to send
        one."""
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "valid": False,
            "message": "Invalid API key format.",
        }
        response = Response()

        with caplog.at_level(logging.INFO):
            result = await _validate_api_key("garbage-not-a-jwt-or-key", _mock_request(), response, api_key_svc)

        _assert_generic_401(result, b"INVALID_API_KEY_FORMAT", b"Invalid API key format.")
        assert "X-User-ID" not in response.headers
        assert any("Invalid API key format." in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
class TestJwtPathIsGeneric:
    async def test_expired_jwt_is_generic(self, caplog):
        cache_svc = AsyncMock()
        with patch("app.routes.validation.get_jwt_verifier") as mock_get_verifier:
            mock_get_verifier.return_value.verify = AsyncMock(side_effect=JWTExpiredError())
            with caplog.at_level(logging.INFO):
                result = await _validate_jwt("token", _mock_request(), Response(), cache_svc)

        _assert_generic_401(result, b"TOKEN_EXPIRED", b"expired")
        assert any("TOKEN_EXPIRED" in r.getMessage() for r in caplog.records)

    async def test_invalid_jwt_is_generic(self, caplog):
        cache_svc = AsyncMock()
        with patch("app.routes.validation.get_jwt_verifier") as mock_get_verifier:
            mock_get_verifier.return_value.verify = AsyncMock(side_effect=JWTVerificationError())
            with caplog.at_level(logging.INFO):
                result = await _validate_jwt("token", _mock_request(), Response(), cache_svc)

        _assert_generic_401(result, b"TOKEN_INVALID", b"invalid")
        assert any("TOKEN_INVALID" in r.getMessage() for r in caplog.records)

    async def test_revoked_jwt_is_generic(self, caplog):
        claims = AuthClaims(
            user_id="user-1",
            tenant_id="1",
            permission_ids=[1, 2, 3],
            roles=[],
            token_type="access_token",
            token_id=None,
            raw={"iat": 1000.0, "sub": "user-1", "type": "access_token"},
        )
        cache_svc = AsyncMock()
        with patch("app.routes.validation.get_jwt_verifier") as mock_get_verifier, \
             patch("app.routes.validation.check_token_revocation", AsyncMock(return_value=True)):
            mock_get_verifier.return_value.verify = AsyncMock(return_value=claims)
            with caplog.at_level(logging.INFO):
                result = await _validate_jwt("token", _mock_request(), Response(), cache_svc)

        _assert_generic_401(result, b"TOKEN_REVOKED", b"revoked")
        assert any("TOKEN_REVOKED" in r.getMessage() for r in caplog.records)
