"""
Tests for the shared JWTVerifier.
"""

import os
import shutil
import tempfile

import pytest

_test_key_dir = tempfile.mkdtemp(prefix="shared-auth-test-keys-")
os.environ["RS256_KEY_DIRECTORY"] = _test_key_dir
os.environ["RS256_MIN_KEY_COUNT"] = "2"
os.environ["ENVIRONMENT"] = "testing"
os.environ["JWT_ISSUER"] = "auth-service"


class TestJWTVerifier:
    """Test the shared library can verify tokens created by auth-service."""

    @pytest.mark.asyncio
    async def test_verify_rs256_token(self):
        """Shared verifier can verify RS256 tokens from auth-service."""
        # Initialize auth-service key manager
        from app.core.security import key_manager
        await key_manager.initialize()

        # Create a token using auth-service
        from app.services.token_service import TokenService
        svc = TokenService()
        token = svc.create_access_token(
            user_id=42,
            tenant_id="t-1",
            permission_ids=[1, 2, 3],
            roles=["USER"],
        )

        # Now verify using the shared library (with direct JWKS, no HTTP)
        from ai4icore_auth.jwt_verifier import JWTVerifier
        verifier = JWTVerifier(issuer="auth-service")
        # Manually inject public keys from key_manager
        from cryptography.hazmat.primitives import serialization
        for pair in key_manager.get_all_public_keys():
            pem = pair.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            verifier.load_public_key(pair.kid, pem)

        claims = await verifier.verify(token)
        assert claims.user_id == 42
        assert claims.tenant_id == "t-1"
        assert claims.permission_ids == [1, 2, 3]
        assert claims.roles == ["USER"]
        assert claims.token_type == "access_token"

    @pytest.mark.asyncio
    async def test_verify_rejects_expired(self):
        """Expired tokens should raise JWTExpiredError."""
        from app.core.security import key_manager
        await key_manager.initialize()

        from app.services.token_service import TokenService
        from datetime import timedelta
        svc = TokenService()
        token = svc.create_access_token(
            user_id=1,
            expires_delta=timedelta(seconds=-10),  # Already expired
        )

        from ai4icore_auth.jwt_verifier import JWTVerifier, JWTExpiredError
        from cryptography.hazmat.primitives import serialization
        verifier = JWTVerifier(issuer="auth-service")
        for pair in key_manager.get_all_public_keys():
            pem = pair.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            verifier.load_public_key(pair.kid, pem)

        with pytest.raises(JWTExpiredError):
            await verifier.verify(token)


class TestPermissionChecker:
    def test_has_permission(self):
        from ai4icore_auth.permission_checker import PermissionChecker
        assert PermissionChecker.has_permission("asr.inference", ["asr.inference", "tts.read"])
        assert not PermissionChecker.has_permission("nmt.inference", ["asr.inference"])

    def test_has_any_role(self):
        from ai4icore_auth.permission_checker import PermissionChecker
        assert PermissionChecker.has_any_role(["ADMIN"], ["USER", "ADMIN"])
        assert not PermissionChecker.has_any_role(["ADMIN"], ["USER"])

    def test_empty_required_passes(self):
        from ai4icore_auth.permission_checker import PermissionChecker
        assert PermissionChecker.has_permission("", ["anything"])


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    shutil.rmtree(_test_key_dir, ignore_errors=True)
