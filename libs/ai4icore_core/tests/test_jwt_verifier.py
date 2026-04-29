"""Tests for ai4icore_core.auth.jwt_verifier.JWTVerifier."""
from __future__ import annotations

import pytest
from jose import jwt as jose_jwt

from ai4icore_core.auth.jwt_verifier import (
    AuthClaims,
    JWTVerifier,
    JWTVerificationError,
    JWTExpiredError,
)


pytestmark = pytest.mark.asyncio


async def test_verify_valid_token_returns_claims(jwt_verifier, token_factory):
    token = token_factory(sub=42, roles=["USER"], permission_ids=[1, 2, 3])
    claims = await jwt_verifier.verify(token)
    assert isinstance(claims, AuthClaims)
    assert claims.user_id == 42
    assert claims.roles == ["USER"]
    assert claims.permission_ids == [1, 2, 3]


async def test_verify_expired_token_raises_jwt_expired(jwt_verifier, token_factory):
    expired = token_factory(ttl_seconds=-10)
    with pytest.raises(JWTExpiredError):
        await jwt_verifier.verify(expired)


async def test_verify_unknown_kid_raises_verification_error(jwt_verifier, token_factory):
    token = token_factory(kid="unknown-key")
    with pytest.raises(JWTVerificationError):
        await jwt_verifier.verify(token)


async def test_verify_wrong_algorithm_rejected(jwt_verifier, rsa_keypair):
    """Token signed with HS256 must be rejected by an RS256-only verifier."""
    payload = {"sub": "1", "exp": 9999999999, "type": "access_token"}
    headers = {"kid": rsa_keypair["kid"]}
    bad = jose_jwt.encode(payload, "shared-secret", algorithm="HS256", headers=headers)
    with pytest.raises(JWTVerificationError):
        await jwt_verifier.verify(bad)


async def test_verify_missing_kid_rejected(jwt_verifier, rsa_keypair):
    payload = {"sub": "1", "exp": 9999999999, "type": "access_token"}
    # Encode without kid header
    no_kid = jose_jwt.encode(
        payload, rsa_keypair["private_pem"], algorithm="RS256",
    )
    with pytest.raises(JWTVerificationError):
        await jwt_verifier.verify(no_kid)


async def test_verify_missing_sub_claim_rejected(jwt_verifier, token_factory, rsa_keypair):
    # Build token with no `sub` and no `user_id`
    import time
    now = int(time.time())
    payload = {"exp": now + 60, "type": "access_token"}
    headers = {"kid": rsa_keypair["kid"]}
    token = jose_jwt.encode(payload, rsa_keypair["private_pem"], algorithm="RS256", headers=headers)
    with pytest.raises(JWTVerificationError):
        await jwt_verifier.verify(token)


async def test_verify_garbage_token_rejected(jwt_verifier):
    with pytest.raises(JWTVerificationError):
        await jwt_verifier.verify("not.a.jwt")


async def test_verify_with_no_keys_loaded_raises():
    v = JWTVerifier()  # no public keys
    with pytest.raises(JWTVerificationError):
        await v.verify("any.token.value")


async def test_verify_falls_back_to_user_id_claim(jwt_verifier, rsa_keypair):
    """When `sub` is missing but `user_id` is present, treat user_id as the subject."""
    import time
    now = int(time.time())
    payload = {
        "user_id": 99,
        "exp": now + 60,
        "type": "access_token",
        "roles": ["USER"],
    }
    headers = {"kid": rsa_keypair["kid"]}
    token = jose_jwt.encode(payload, rsa_keypair["private_pem"], algorithm="RS256", headers=headers)
    claims = await jwt_verifier.verify(token)
    assert claims.user_id == 99
