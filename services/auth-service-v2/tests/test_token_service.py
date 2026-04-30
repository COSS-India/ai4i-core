"""
Tests for the TokenService — RS256 JWT creation and validation.
"""

import os
import shutil
import tempfile

import pytest

# Set up test key directory before imports
_test_key_dir = tempfile.mkdtemp(prefix="auth-test-keys-")
os.environ["RS256_KEY_DIRECTORY"] = _test_key_dir
os.environ["RS256_MIN_KEY_COUNT"] = "2"
os.environ["ENVIRONMENT"] = "testing"


@pytest.fixture(scope="module", autouse=True)
async def setup_keys():
    """Initialize RSA keys for testing."""
    from app.core.security import key_manager
    await key_manager.initialize()
    yield
    shutil.rmtree(_test_key_dir, ignore_errors=True)


class TestTokenService:
    def _get_service(self):
        from app.services.token_service import TokenService
        return TokenService()

    @pytest.mark.asyncio
    async def test_create_and_validate_access_token(self, setup_keys):
        svc = self._get_service()
        token = svc.create_access_token(
            user_id=1,
            tenant_id="tenant-123",
            permission_ids=[1, 2, 3],
            roles=["USER"],
        )
        assert isinstance(token, str)
        assert len(token) > 50

        # Validate
        payload = svc.validate_token(token)
        assert payload.sub == "1"
        assert payload.tenant_id == "tenant-123"
        assert payload.permission_ids == [1, 2, 3]
        assert payload.roles == ["USER"]
        assert payload.token_type == "access_token"
        assert payload.token_id is None

    @pytest.mark.asyncio
    async def test_create_and_validate_refresh_token(self, setup_keys):
        svc = self._get_service()
        token, token_id = svc.create_refresh_token(
            user_id=42,
            tenant_id="t-1",
            roles=["ADMIN"],
        )
        assert isinstance(token, str)
        assert isinstance(token_id, str)
        assert len(token_id) == 36  # UUID

        payload = svc.validate_token(token)
        assert payload.sub == "42"
        assert payload.token_type == "refresh"
        assert payload.token_id == token_id

    @pytest.mark.asyncio
    async def test_create_and_validate_api_key_token(self, setup_keys):
        svc = self._get_service()
        token_id = "test-api-key-id-1234"
        token = svc.create_api_key_token(
            user_id=10,
            token_id=token_id,
            tenant_id="t-2",
            permission_ids=[5, 6],
        )
        assert isinstance(token, str)

        payload = svc.validate_token(token)
        assert payload.sub == "10"
        assert payload.token_type == "api_key"
        assert payload.token_id == token_id
        assert payload.permission_ids == [5, 6]

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self, setup_keys):
        from app.core.exceptions import TokenInvalidError
        svc = self._get_service()
        with pytest.raises(TokenInvalidError):
            svc.validate_token("invalid.jwt.token")

    @pytest.mark.asyncio
    async def test_jwks_endpoint(self, setup_keys):
        from app.core.security import key_manager
        jwks = key_manager.get_jwks()
        assert "keys" in jwks
        assert len(jwks["keys"]) >= 2
        for key in jwks["keys"]:
            assert key["kty"] == "RSA"
            assert key["alg"] == "RS256"
            assert "kid" in key
            assert "n" in key
            assert "e" in key


class TestPasswordManager:
    def test_hash_and_verify(self):
        from app.core.security import password_manager
        result = password_manager.hash_password("SecureP@ss1")
        assert result.hashed
        assert result.salt
        assert result.rounds > 0

        # Verify with correct password
        assert password_manager.verify_password("SecureP@ss1", result.hashed, result.salt) is True

        # Verify with wrong password
        assert password_manager.verify_password("WrongPass1!", result.hashed, result.salt) is False

    def test_validate_strength(self):
        from app.core.security import password_manager
        valid, errors = password_manager.validate_strength("Str0ng!Pass")
        assert valid is True
        assert errors == []

        valid, errors = password_manager.validate_strength("weak")
        assert valid is False
        assert len(errors) > 0
