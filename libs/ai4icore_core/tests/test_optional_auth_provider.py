"""Tests for ai4icore_core.auth.providers.OptionalAuthProvider.

Critical security invariant: token-related failures (invalid / expired / revoked)
become anonymous (None), but infrastructure failures (Redis outage, JWKS fetch
error, etc.) MUST propagate so transient backend issues do not silently
downgrade a request to anonymous.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import Request

from ai4icore_core.auth.jwt_verifier import (
    JWTExpiredError,
    JWTRevokedError,
    JWTVerificationError,
)


pytestmark = pytest.mark.asyncio


def _fake_request() -> Request:
    return Request(scope={"type": "http", "headers": [], "method": "GET", "path": "/"})


def _build_provider(jwt_verifier):
    """Build OptionalAuthProvider with a pre-configured verifier (no env / network)."""
    from ai4icore_core.auth import providers as providers_module

    with patch.object(providers_module, "build_jwt_verifier", return_value=jwt_verifier), \
         patch.object(providers_module, "_is_auth_disabled", return_value=False):
        _, optional = providers_module.create_auth_providers()
    return optional


async def test_no_authorization_returns_none(jwt_verifier):
    """No header → anonymous."""
    optional = _build_provider(jwt_verifier)
    result = await optional(request=_fake_request(), authorization=None)
    assert result is None


async def test_valid_token_returns_claims(jwt_verifier, token_factory):
    optional = _build_provider(jwt_verifier)
    token = token_factory(sub=11, roles=["USER"])
    claims = await optional(request=_fake_request(), authorization=f"Bearer {token}")
    assert claims is not None
    assert claims.user_id == 11


async def test_expired_token_returns_none_silently(jwt_verifier, token_factory):
    """Token-related failure → silent anonymous."""
    optional = _build_provider(jwt_verifier)
    expired = token_factory(ttl_seconds=-10)
    result = await optional(request=_fake_request(), authorization=f"Bearer {expired}")
    assert result is None


async def test_invalid_token_returns_none_silently(jwt_verifier):
    optional = _build_provider(jwt_verifier)
    result = await optional(request=_fake_request(), authorization="Bearer garbage.token.here")
    assert result is None


async def test_infrastructure_error_propagates(jwt_verifier):
    """
    Critical: a Redis outage / JWKS fetch failure / generic RuntimeError must
    NOT be silently downgraded to anonymous. Otherwise an attacker who can
    trigger a transient backend error gains unauthenticated access to
    optional-auth endpoints.
    """
    from ai4icore_core.auth import providers as providers_module

    with patch.object(providers_module, "build_jwt_verifier", return_value=jwt_verifier), \
         patch.object(providers_module, "_is_auth_disabled", return_value=False):
        AuthProvider, OptionalAuthProvider = providers_module.create_auth_providers()

    # Replace the inner AuthProvider with one that raises a non-auth exception.
    # We do this by patching the closure reference — easiest way is to wrap
    # OptionalAuthProvider in a thin shim that simulates the failure.
    async def _failing_inner(*a, **kw):
        raise RuntimeError("simulated Redis outage")

    # Monkey-patch the module-level inner function path: rebuild via direct call
    # using a custom JWTVerifier.verify that raises RuntimeError mid-flight.
    async def _verify(_token):
        raise RuntimeError("simulated JWKS unreachable")

    with patch.object(jwt_verifier, "verify", side_effect=_verify):
        with pytest.raises(RuntimeError, match="JWKS unreachable"):
            await OptionalAuthProvider(
                request=_fake_request(),
                authorization="Bearer some.real-looking.token",
            )


async def test_jwt_specific_exceptions_listed_explicitly():
    """
    Whitelist of swallowed exceptions must be auth-specific.
    Guards against future regressions to a bare `except Exception`.
    """
    import inspect

    from ai4icore_core.auth import providers as providers_module

    src = inspect.getsource(providers_module)
    # The narrowed except must list at least these auth-only types
    assert "JWTVerificationError" in src
    assert "JWTExpiredError" in src
    assert "JWTRevokedError" in src
    # Bare 'except Exception:' inside OptionalAuthProvider would be a regression
    # (heuristic — not bulletproof, but catches the common reintroduction)
    assert "except Exception" not in src.split("OptionalAuthProvider", 1)[1]
