"""Regression test for the /auth/validate JWT path's revocation gate.

Historically `_validate_jwt` only called `check_token_revocation` when
`claims.token_id` was truthy. Access tokens carry `jti`, not `token_id`
(only api_key tokens set token_id — see token_service.py's docstring), so
`claims.token_id` is always None for access tokens. That gate silently
skipped revocation checking — including global-logout revocation — for
every access token, with none of the unit tests on check_token_revocation
itself catching it since they call it directly and never go through this
gate. This test exercises _validate_jwt end-to-end (verify -> gate ->
revocation check) so a re-introduced token_id gate fails loudly.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

from app.core.jwt_verifier import AuthClaims
from app.routes.validation import _validate_jwt


def _access_token_claims(user_id: str, iat: float) -> AuthClaims:
    """Build claims shaped exactly like a real access token: token_id is
    None (no `token_id` claim — only `jti`, which AuthClaims doesn't
    surface as a field), token_type is "access_token"."""
    return AuthClaims(
        user_id=user_id,
        tenant_id="1",
        permission_ids=[1, 2, 3],
        roles=[],
        token_type="access_token",
        token_id=None,
        raw={"iat": iat, "sub": user_id, "type": "access_token"},
    )


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.headers = {}  # no X-Original-Method/URI -> endpoint check passes through
    return request


@pytest.mark.asyncio
class TestValidateJwtRevocationGate:
    async def test_access_token_revoked_after_global_logout_returns_401(self):
        claims = _access_token_claims("user-1", iat=1000.0)
        cache_svc = AsyncMock()

        with patch("app.routes.validation.get_jwt_verifier") as mock_get_verifier, \
             patch("app.routes.validation.check_token_revocation", AsyncMock(return_value=True)) as mock_check:
            mock_get_verifier.return_value.verify = AsyncMock(return_value=claims)

            result = await _validate_jwt("token", _mock_request(), Response(), cache_svc)

        assert result.status_code == 401
        assert b"TOKEN_REVOKED" in result.body
        # Must be called even though claims.token_id is None — this is the
        # exact case the old `if claims.token_id and ...` gate broke.
        mock_check.assert_awaited_once()
        _, kwargs = mock_check.call_args
        assert kwargs["user_id"] == "user-1"
        assert kwargs["issued_at"] == 1000.0

    async def test_access_token_not_revoked_returns_valid(self):
        claims = _access_token_claims("11111111-1111-1111-1111-111111111111", iat=1000.0)
        cache_svc = AsyncMock()

        with patch("app.routes.validation.get_jwt_verifier") as mock_get_verifier, \
             patch("app.routes.validation.check_token_revocation", AsyncMock(return_value=False)):
            mock_get_verifier.return_value.verify = AsyncMock(return_value=claims)

            result = await _validate_jwt("token", _mock_request(), Response(), cache_svc)

        assert result.valid is True
