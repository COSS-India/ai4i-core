"""
Shared RS256 JWT verifier for all microservices.

This is the SINGLE source of truth for JWT validation across the platform.
Every service imports and uses this — no service-local JWT verification.

RS256 only — JWKS-based public key verification.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from jose import jwt, JWTError, ExpiredSignatureError

from ai4icore_exceptions import (
    TokenExpiredError,
    TokenRevokedError,
    TokenInvalidError,
)

logger = logging.getLogger(__name__)


@dataclass
class AuthClaims:
    """Verified JWT claims — the standard auth context for all services."""

    user_id: int
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


class JWTRevokedError(TokenRevokedError):
    """Extends shared TokenRevokedError (401)."""
    pass


class JWTVerifier:
    """
    RS256 JWT verifier that loads public keys from JWKS endpoint.

    Usage in any microservice::

        from ai4icore_auth.providers import build_jwt_verifier

        verifier = build_jwt_verifier()  # reads JWKS_URL, JWT_ISSUER from env
        await verifier.initialize()

        claims = await verifier.verify(token)
        print(claims.user_id, claims.tenant_id, claims.roles)
    """

    def __init__(
        self,
        jwks_url: Optional[str] = None,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._jwks: dict[str, Any] = {}
        self._public_keys: dict[str, bytes] = {}  # kid → PEM bytes

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
            logger.warning("JWTVerifier: no JWKS URL configured and no keys loaded.")

    async def _refresh_jwks(self) -> None:
        """Fetch the JWKS from the auth service."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self._jwks_url)
                resp.raise_for_status()
                self._jwks = resp.json()

            self._public_keys = {}
            for jwk in self._jwks.get("keys", []):
                kid = jwk.get("kid")
                if kid:
                    try:
                        pem = self._jwk_to_pem(jwk)
                        self._public_keys[kid] = pem
                    except (ValueError, KeyError):
                        logger.warning("Failed to convert JWK kid=%s to PEM", kid)

            logger.info("JWKS refreshed: %d public key(s) loaded from %s", len(self._public_keys), self._jwks_url)

        except httpx.HTTPError as exc:
            if not self._public_keys:
                raise RuntimeError(f"Cannot load JWKS from {self._jwks_url}: {exc}")
            logger.error(
                "JWKS refresh failed — using %d stale key(s). "
                "Token verification may accept revoked keys. Error: %s",
                len(self._public_keys), exc,
            )

    @staticmethod
    def _jwk_to_pem(jwk: dict) -> bytes:
        """Convert a JWK RSA public key to PEM bytes."""
        import base64
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        def _b64url_decode(data: str) -> bytes:
            padding = 4 - len(data) % 4
            return base64.urlsafe_b64decode(data + "=" * padding)

        if "n" not in jwk or "e" not in jwk:
            raise ValueError("JWK missing required 'n' or 'e' field.")
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
            raise JWTVerificationError("No verification keys available.")

        try:
            header = jwt.get_unverified_header(token)
        except JWTError:
            raise JWTVerificationError("Invalid token header.")

        kid = header.get("kid")
        alg = header.get("alg")

        if not kid:
            raise JWTVerificationError("Token header missing 'kid'.")
        if alg is not None and alg != "RS256":
            raise JWTVerificationError(f"Unsupported algorithm '{alg}'. Expected RS256.")

        pem = self._public_keys.get(kid)
        if not pem:
            raise JWTVerificationError(f"Unknown key ID '{kid}'.")

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
        except ExpiredSignatureError:
            raise JWTExpiredError()
        except JWTError as exc:
            logger.debug("RS256 verification failed: %s", exc)
            raise JWTVerificationError("Token verification failed.")

        return self._payload_to_claims(payload)

    @staticmethod
    def _payload_to_claims(payload: dict[str, Any]) -> AuthClaims:
        """Convert raw JWT payload to AuthClaims."""
        sub = payload.get("sub")
        if sub is None:
            sub = payload.get("user_id")
        if sub is None:
            raise JWTVerificationError("Token missing 'sub' claim.")

        try:
            user_id = int(sub)
        except (TypeError, ValueError):
            raise JWTVerificationError("Invalid 'sub' claim.")

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
