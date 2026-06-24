"""
Shared RS256 JWT verifier for all microservices.

This is the SINGLE source of truth for JWT validation across the platform.
Every service imports and uses this — no service-local JWT verification.

RS256 only — JWKS-based public key verification.
"""

import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
import jwt
from jwt.exceptions import PyJWTError, ExpiredSignatureError
import httpx

from ai4i_core.exceptions import (
    TokenExpiredError,
    TokenInvalidError,
)
from app.core.messages import (
    TOKEN_NO_KEYS,
    TOKEN_HEADER_INVALID,
    TOKEN_MISSING,
    TOKEN_ALGORITHM_UNSUPPORTED,
    TOKEN_MISSING_SUB,
    TOKEN_INVALID,
    JWK_MISSING_FIELDS,
    LOG_WARN_JWT_NO_KEYS,
    LOG_WARN_JWK_CONVERT_FAILED,
    LOG_JWKS_REFRESHED,
    LOG_ERROR_JWKS_LOAD_FAILED,
    LOG_ERROR_JWKS_REFRESH_FAILED,
    LOG_DEBUG_RS256_VERIFICATION_FAILED,
)

logger = logging.getLogger(__name__)


@dataclass
class AuthClaims:
    """Verified JWT claims — the standard auth context for all services."""

    user_id: Any  # str (UUID) or int depending on the service
    tenant_id: Optional[str] = None
    permission_ids: list[int] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    token_type: str = ""
    token_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    raw: dict = field(default_factory=dict)


# JWT exceptions extend the shared platform hierarchy
# so register_exception_handlers() catches them automatically.

class JWTVerificationError(TokenInvalidError):
    """Raised when JWT verification fails. Extends shared TokenInvalidError (401)."""

    def __init__(self, message: str = "JWT verification failed.", code: str = "JWT_VERIFICATION_FAILED"):
        # TokenInvalidError.__init__ takes message only; set code manually
        super().__init__(message=message)
        self.code = code


class JWTExpiredError(TokenExpiredError):
    """Extends shared TokenExpiredError (401)."""
    pass


class JWTVerifier:
    """
    RS256 JWT verifier that loads public keys from JWKS endpoint.

    Only used by auth-service to validate tokens for the /auth/validate endpoint.
    Backend services no longer perform JWT verification; the gateway validates all tokens.
    """

    def __init__(
        self,
        jwks_url: Optional[str] = None,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
        http_timeout_seconds: float = 10.0,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._http_timeout_seconds = http_timeout_seconds
        self._public_keys: dict[str, bytes] = {}  # kid → PEM bytes
        self._last_jwks_refresh: float = 0.0  # monotonic; guards against per-request DoS

    # ── Public key management ──

    def load_public_key(self, kid: str, pem_bytes: bytes) -> None:
        """
        Register a public key by kid. Public API for services that have
        direct access to key material (e.g., auth-service itself).

        Args:
            kid: Key identifier matching the 'kid' JWT header.
            pem_bytes: PEM-encoded RSA public key bytes.
        """
        self._public_keys[kid] = pem_bytes

    @property
    def loaded_key_count(self) -> int:
        """Number of public keys currently loaded."""
        return len(self._public_keys)

    async def initialize(self) -> None:
        """Fetch JWKS from the auth service. Call during app startup."""
        if self._jwks_url:
            await self._refresh_jwks()
        elif not self._public_keys:
            logger.warning(LOG_WARN_JWT_NO_KEYS)

    async def _refresh_jwks(self) -> None:
        """Fetch the JWKS from the auth service."""
        try:
            async with httpx.AsyncClient(timeout=self._http_timeout_seconds) as client:
                resp = await client.get(self._jwks_url)
                resp.raise_for_status()
                jwks = resp.json()

            self._public_keys = {}
            for jwk in jwks.get("keys", []):
                kid = jwk.get("kid")
                if kid:
                    try:
                        pem = self._jwk_to_pem(jwk)
                        self._public_keys[kid] = pem
                    except (ValueError, KeyError):
                        logger.warning(LOG_WARN_JWK_CONVERT_FAILED, kid)

            logger.info(LOG_JWKS_REFRESHED, len(self._public_keys), self._jwks_url)

        except httpx.HTTPError as exc:
            if not self._public_keys:
                raise RuntimeError(LOG_ERROR_JWKS_LOAD_FAILED.format(url=self._jwks_url, error=exc)) from exc
            logger.error(LOG_ERROR_JWKS_REFRESH_FAILED, len(self._public_keys), exc)

    @staticmethod
    def _jwk_to_pem(jwk: dict) -> bytes:
        """Convert a JWK RSA public key to PEM bytes."""
        def _b64url_decode(data: str) -> bytes:
            padding = 4 - len(data) % 4
            return base64.urlsafe_b64decode(data + "=" * padding)

        if "n" not in jwk or "e" not in jwk:
            raise ValueError(JWK_MISSING_FIELDS)
        n = int.from_bytes(_b64url_decode(jwk["n"]), byteorder="big")
        e = int.from_bytes(_b64url_decode(jwk["e"]), byteorder="big")

        public_numbers = RSAPublicNumbers(e=e, n=n)
        public_key = public_numbers.public_key(default_backend())
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    async def verify(self, token: str) -> AuthClaims:
        """
        Verify a JWT token using RS256.
        Returns AuthClaims on success, raises JWTVerificationError on failure.
        """
        if not self._public_keys:
            raise JWTVerificationError(TOKEN_NO_KEYS)

        # Header-only read to pick the right public key by ``kid`` before
        # signature verification. The signature is verified below by
        # ``jwt.decode(token, pem, algorithms=["RS256"], ...)``. This is the
        # JWKS kid-selection pattern that python:S5659 itself recommends.
        try:
            header = jwt.get_unverified_header(token)  # NOSONAR
        except PyJWTError as exc:
            raise JWTVerificationError(TOKEN_HEADER_INVALID) from exc

        kid = header.get("kid")
        alg = header.get("alg")

        if not kid:
            raise JWTVerificationError(TOKEN_MISSING)
        if alg != "RS256":
            raise JWTVerificationError(TOKEN_ALGORITHM_UNSUPPORTED)

        pem = self._public_keys.get(kid)
        if pem is None and self._jwks_url:
            # On key-miss, attempt one refresh per 30s — handles key rotation
            # without restart while bounding outbound HTTP calls per unknown kid.
            if time.monotonic() - self._last_jwks_refresh >= 30.0:
                try:
                    await self._refresh_jwks()
                    self._last_jwks_refresh = time.monotonic()
                    pem = self._public_keys.get(kid)
                except Exception as exc:
                    self._last_jwks_refresh = time.monotonic()  # back off even on failure
                    logger.debug("JWKS refresh failed during key-rotation attempt: %s", exc)
        if pem is None:
            raise JWTVerificationError(TOKEN_INVALID)

        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": {"verify_exp": True},
        }
        if self._issuer:
            decode_kwargs["issuer"] = self._issuer
        if self._audience:
            decode_kwargs["audience"] = self._audience

        try:
            payload = jwt.decode(token, pem, **decode_kwargs)
        except ExpiredSignatureError as exc:
            raise JWTExpiredError() from exc
        except PyJWTError as exc:
            logger.debug(LOG_DEBUG_RS256_VERIFICATION_FAILED, exc)
            raise JWTVerificationError(TOKEN_INVALID) from exc

        return self._payload_to_claims(payload)

    @staticmethod
    def _payload_to_claims(payload: dict[str, Any]) -> AuthClaims:
        """Convert raw JWT payload to AuthClaims."""
        sub = payload.get("sub")
        if sub is None:
            sub = payload.get("user_id")
        if sub is None:
            raise JWTVerificationError(TOKEN_MISSING_SUB)

        try:
            user_id = int(sub)
        except (TypeError, ValueError):
            user_id = sub  # UUID string or other non-integer identifier

        return AuthClaims(
            user_id=user_id,
            tenant_id=payload.get("tenant_id"),
            permission_ids=payload.get("permission_ids", []),
            roles=payload.get("roles", []),
            token_type=payload.get("type", ""),
            token_id=payload.get("token_id"),
            username=payload.get("username"),
            email=payload.get("email"),
            raw=payload,
        )
