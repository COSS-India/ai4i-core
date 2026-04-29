"""Shared pytest fixtures for ai4icore_core tests."""
from __future__ import annotations

import time
from typing import Any

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

from ai4icore_core.auth.jwt_verifier import JWTVerifier


# ── RSA keypair (one per session) ──

@pytest.fixture(scope="session")
def rsa_keypair() -> dict[str, Any]:
    """Generate a fresh RSA keypair and return PEM bytes for both sides."""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {"kid": "test-key-1", "private_pem": private_pem, "public_pem": public_pem}


@pytest.fixture
def jwt_verifier(rsa_keypair: dict[str, Any]) -> JWTVerifier:
    """A JWTVerifier with the test public key already loaded."""
    v = JWTVerifier()
    v.load_public_key(rsa_keypair["kid"], rsa_keypair["public_pem"])
    return v


# ── Token factory ──

def _sign(payload: dict, kid: str, private_pem: bytes, alg: str = "RS256") -> str:
    headers = {"kid": kid}
    return jose_jwt.encode(payload, private_pem, algorithm=alg, headers=headers)


@pytest.fixture
def token_factory(rsa_keypair):
    """Build signed JWT tokens with sensible defaults; allow per-test overrides."""
    def _make(
        sub: str | int = 42,
        roles: list[str] | None = None,
        permission_ids: list[int] | None = None,
        ttl_seconds: int = 60,
        alg: str = "RS256",
        kid: str | None = None,
        extra: dict | None = None,
    ) -> str:
        now = int(time.time())
        payload = {
            "sub": str(sub),
            "iat": now,
            "exp": now + ttl_seconds,
            "type": "access_token",
            "roles": roles or [],
            "permission_ids": permission_ids or [],
        }
        if extra:
            payload.update(extra)
        return _sign(payload, kid or rsa_keypair["kid"], rsa_keypair["private_pem"], alg=alg)

    return _make
