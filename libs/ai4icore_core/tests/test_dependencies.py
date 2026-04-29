"""Tests for ai4icore_core.auth.dependencies.create_require_auth.

Covers:
  • missing Authorization header → AuthenticationRequiredError
  • malformed bearer token       → AuthenticationRequiredError or TokenInvalidError
  • valid token                  → returns AuthClaims and populates request.state
  • expired token                → TokenExpiredError
"""
from __future__ import annotations

import pytest
from fastapi import Request

from ai4icore_core.auth.dependencies import create_require_auth
from ai4icore_core.exceptions import (
    AuthenticationRequiredError,
    TokenExpiredError,
    TokenInvalidError,
)


pytestmark = pytest.mark.asyncio


def _fake_request() -> Request:
    """Minimal Starlette Request for state population assertions."""
    return Request(scope={"type": "http", "headers": [], "method": "GET", "path": "/"})


async def test_require_auth_no_header_raises_authentication_required(jwt_verifier):
    require_auth = create_require_auth(jwt_verifier)
    with pytest.raises(AuthenticationRequiredError):
        await require_auth(request=_fake_request(), authorization=None)


async def test_require_auth_empty_bearer_raises_authentication_required(jwt_verifier):
    require_auth = create_require_auth(jwt_verifier)
    with pytest.raises(AuthenticationRequiredError):
        await require_auth(request=_fake_request(), authorization="Bearer ")


async def test_require_auth_malformed_token_raises_token_invalid(jwt_verifier):
    require_auth = create_require_auth(jwt_verifier)
    with pytest.raises(TokenInvalidError):
        await require_auth(request=_fake_request(), authorization="Bearer not.a.jwt")


async def test_require_auth_expired_token_raises_token_expired(jwt_verifier, token_factory):
    expired = token_factory(ttl_seconds=-10)
    require_auth = create_require_auth(jwt_verifier)
    with pytest.raises(TokenExpiredError):
        await require_auth(request=_fake_request(), authorization=f"Bearer {expired}")


async def test_require_auth_valid_token_returns_claims_and_populates_state(
    jwt_verifier, token_factory
):
    token = token_factory(sub=42, roles=["USER"], permission_ids=[1, 2])
    require_auth = create_require_auth(jwt_verifier)
    request = _fake_request()
    claims = await require_auth(request=request, authorization=f"Bearer {token}")

    # Returned claims
    assert claims.user_id == 42
    assert claims.roles == ["USER"]
    assert claims.permission_ids == [1, 2]

    # request.state populated for downstream handlers
    assert request.state.user_id == 42
    assert request.state.is_authenticated is True
    assert request.state.roles == ["USER"]
    assert request.state.permission_ids == [1, 2]


async def test_require_auth_accepts_raw_token_without_bearer_prefix(
    jwt_verifier, token_factory
):
    """Some clients send the bare JWT — verifier should still accept it."""
    token = token_factory(sub=7)
    require_auth = create_require_auth(jwt_verifier)
    claims = await require_auth(request=_fake_request(), authorization=token)
    assert claims.user_id == 7
