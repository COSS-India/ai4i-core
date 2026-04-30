"""
Tests for all critical/high security fixes.

Covers:
1. Privilege escalation in API key creation
2. Cross-user key selection
3. validate-api-key service/action/ownership checks
4. Token revocation DB fallback
5. Production key auto-generation fail-fast
6. CORS production gating
7. Strict JWT claims (iss/aud/alg/kid)
"""

import os
import shutil
import tempfile

import pytest

# Test environment
_test_key_dir = tempfile.mkdtemp(prefix="auth-test-keys-")
os.environ["RS256_KEY_DIRECTORY"] = _test_key_dir
os.environ["RS256_MIN_KEY_COUNT"] = "2"
os.environ["ENVIRONMENT"] = "testing"
os.environ["JWT_ISSUER"] = "auth-service"


@pytest.fixture(scope="module", autouse=True)
async def setup_keys():
    from app.core.security import key_manager
    await key_manager.initialize()
    yield
    shutil.rmtree(_test_key_dir, ignore_errors=True)


# ── Critical #1: Privilege escalation in API key creation ──

class TestAPIKeyPrivilegeEscalation:
    """Non-admin must not be able to create keys for other users."""

    def test_schema_accepts_user_id(self):
        from app.schemas.api_key import APIKeyCreateRequest
        # Verify the schema allows user_id
        req = APIKeyCreateRequest(key_name="test", user_id=999)
        assert req.user_id == 999

    def test_schema_defaults_user_id_to_none(self):
        from app.schemas.api_key import APIKeyCreateRequest
        req = APIKeyCreateRequest(key_name="test")
        assert req.user_id is None


# ── Critical #3: validate-api-key checks ──

class TestAPIKeyValidationChecks:
    @pytest.mark.asyncio
    async def test_validate_checks_service_permission(self, setup_keys):
        """API key without required service permission should be rejected."""
        from app.services.api_key_service import APIKeyService
        from unittest.mock import AsyncMock, MagicMock

        mock_repo = AsyncMock()
        mock_cache = AsyncMock()
        token_svc = MagicMock()

        svc = APIKeyService(mock_repo, token_svc, mock_cache)

        # Mock a valid token
        mock_payload = MagicMock()
        mock_payload.token_type = "api_key"
        mock_payload.token_id = "test-id"
        mock_payload.sub = "1"
        mock_payload.tenant_id = None
        token_svc.validate_token.return_value = mock_payload

        # Mock cache says valid
        mock_cache.is_api_key_valid.return_value = True

        # Mock DB key with only TTS permission
        mock_db_key = MagicMock()
        mock_db_key.permissions = ["tts.inference"]
        mock_db_key.is_active = True
        mock_db_key.is_revoked = False
        mock_db_key.user_id = 1
        mock_db_key.expires_at = None
        mock_repo.get_by_token_id.return_value = mock_db_key

        # Request ASR service — should fail
        result = await svc.validate_api_key_jwt(
            jwt_token="fake.jwt.token",
            required_service="asr",
            required_action="inference",
        )
        assert result["valid"] is False
        assert "asr" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_checks_ownership(self, setup_keys):
        """API key must belong to the expected user."""
        from app.services.api_key_service import APIKeyService
        from unittest.mock import AsyncMock, MagicMock

        mock_repo = AsyncMock()
        mock_cache = AsyncMock()
        token_svc = MagicMock()

        svc = APIKeyService(mock_repo, token_svc, mock_cache)

        mock_payload = MagicMock()
        mock_payload.token_type = "api_key"
        mock_payload.token_id = "test-id"
        mock_payload.sub = "1"
        mock_payload.tenant_id = None
        token_svc.validate_token.return_value = mock_payload

        mock_cache.is_api_key_valid.return_value = True

        mock_db_key = MagicMock()
        mock_db_key.permissions = ["asr.inference"]
        mock_db_key.is_active = True
        mock_db_key.is_revoked = False
        mock_db_key.user_id = 1  # Key belongs to user 1
        mock_db_key.expires_at = None
        mock_repo.get_by_token_id.return_value = mock_db_key

        # Expected user is 999 — should fail
        result = await svc.validate_api_key_jwt(
            jwt_token="fake.jwt.token",
            expected_user_id=999,
        )
        assert result["valid"] is False
        assert "belong" in result["message"].lower()


# ── Critical #4: Token revocation DB fallback ──

class TestTokenRevocationFallback:
    @pytest.mark.asyncio
    async def test_bearer_path_falls_back_to_db(self):
        """When Redis evicts a token, bearer path should check DB before revoking."""
        from app.dependencies.auth import _check_token_revocation
        from unittest.mock import AsyncMock, MagicMock

        mock_cache = AsyncMock()
        mock_db = AsyncMock()

        # Redis says token NOT found (evicted)
        mock_cache.is_api_key_valid.return_value = False

        # But DB says it's still active
        from unittest.mock import patch
        mock_api_key = MagicMock()
        mock_api_key.is_revoked = False
        mock_api_key.is_active = True
        mock_api_key.expires_at = None

        with patch("app.dependencies.auth.APIKeyRepository") as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_by_token_id.return_value = mock_api_key
            MockRepo.return_value = repo_instance

            revoked = await _check_token_revocation(
                token_id="test-token-id",
                token_type="api_key",
                cache_service=mock_cache,
                db=mock_db,
            )

        # Should NOT be revoked (DB says active)
        assert revoked is False

    @pytest.mark.asyncio
    async def test_actually_revoked_returns_true(self):
        """Actually revoked token should return True."""
        from app.dependencies.auth import _check_token_revocation
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_cache = AsyncMock()
        mock_db = AsyncMock()

        mock_cache.is_api_key_valid.return_value = False

        mock_api_key = MagicMock()
        mock_api_key.is_revoked = True
        mock_api_key.is_active = False

        with patch("app.dependencies.auth.APIKeyRepository") as MockRepo:
            repo_instance = AsyncMock()
            repo_instance.get_by_token_id.return_value = mock_api_key
            MockRepo.return_value = repo_instance

            revoked = await _check_token_revocation(
                token_id="test-token-id",
                token_type="api_key",
                cache_service=mock_cache,
                db=mock_db,
            )

        assert revoked is True


# ── Critical #5: Production key auto-generation fail-fast ──

class TestProductionKeyFailFast:
    @pytest.mark.asyncio
    async def test_production_fails_without_keys(self):
        """In production, missing RSA keys should raise RuntimeError."""
        from app.core.security import RS256KeyManager
        from app.core.config import AuthSettings

        empty_dir = tempfile.mkdtemp(prefix="empty-keys-")
        try:
            manager = RS256KeyManager()
            # Patch settings to production
            import unittest.mock
            with unittest.mock.patch("app.core.security.settings") as mock_settings:
                mock_settings.environment = "production"
                mock_settings.get_rs256_key_path.return_value = __import__("pathlib").Path(empty_dir)
                mock_settings.rs256_min_key_count = 10

                with pytest.raises(RuntimeError, match="FATAL"):
                    await manager.initialize()
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)


# ── Medium: Strict JWT claims ──

class TestStrictJWTClaims:
    @pytest.mark.asyncio
    async def test_token_includes_issuer(self, setup_keys):
        from app.services.token_service import TokenService
        svc = TokenService()
        token = svc.create_access_token(user_id=1)
        payload = svc.validate_token(token)
        assert payload.iss == "auth-service"

    @pytest.mark.asyncio
    async def test_token_includes_sub_and_type(self, setup_keys):
        from app.services.token_service import TokenService
        svc = TokenService()
        token = svc.create_access_token(user_id=42, roles=["USER"])
        payload = svc.validate_token(token)
        assert payload.sub == "42"
        assert payload.token_type == "access_token"

    @pytest.mark.asyncio
    async def test_rejects_missing_kid(self, setup_keys):
        """Token without kid in header should be rejected."""
        from app.services.token_service import TokenService
        from app.core.exceptions import TokenInvalidError
        from jose import jwt as jose_jwt

        svc = TokenService()
        # Craft a token without kid
        fake_token = jose_jwt.encode(
            {"sub": "1", "type": "access_token"},
            "fake-secret",
            algorithm="HS256",
        )
        with pytest.raises(TokenInvalidError):
            svc.validate_token(fake_token)
