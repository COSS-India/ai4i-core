"""
JWT token creation and validation (RS256 only).

Strict JWT contract:
- All tokens include: iss (issuer), kid (key ID), alg (RS256)
- Access tokens: type=access_token, no token_id
- Refresh tokens: type=refresh, token_id (UUID) for revocation
- API key tokens: type=api_key, token_id (UUID) for revocation
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import jwt, JWTError
from cryptography.hazmat.primitives import serialization

from app.core.config import settings
from app.core.security import key_manager

logger = logging.getLogger(__name__)


class TokenPayload:
    """Decoded JWT payload."""

    def __init__(self, data: dict[str, Any]):
        self.sub: str = str(data.get("sub", ""))
        self.tenant_id: Optional[str] = data.get("tenant_id")
        self.permission_ids: list[int] = data.get("permission_ids", [])
        self.roles: list[str] = data.get("roles", [])
        self.token_type: str = data.get("type", "")
        self.token_id: Optional[str] = data.get("token_id")
        self.exp: Optional[datetime] = None
        self.iss: Optional[str] = data.get("iss")
        self.aud: Optional[str] = data.get("aud")
        self.kid: Optional[str] = data.get("kid")
        self.raw = data

        if "exp" in data:
            self.exp = datetime.fromtimestamp(data["exp"], tz=timezone.utc)


class TokenService:
    """Creates and validates RS256 JWT tokens with strict iss/aud/alg/kid claims."""

    def _base_claims(self) -> dict[str, Any]:
        """Standard claims included in every token."""
        claims: dict[str, Any] = {
            "iss": settings.jwt_issuer,
            "iat": datetime.now(timezone.utc),
            "kid": key_manager.get_signing_kid(),
        }
        if settings.jwt_audience:
            claims["aud"] = settings.jwt_audience
        return claims

    # ── Creation ──

    def create_access_token(
        self,
        user_id: int,
        tenant_id: Optional[str] = None,
        permission_ids: list[int] | None = None,
        roles: list[str] | None = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a short-lived access token (default 1 hour)."""
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))

        payload = {
            **self._base_claims(),
            "sub": str(user_id),
            "tenant_id": tenant_id,
            "permission_ids": permission_ids or [],
            "roles": roles or [],
            "type": "access_token",
            "exp": expire,
        }
        return self._sign(payload)

    def create_refresh_token(
        self,
        user_id: int,
        tenant_id: Optional[str] = None,
        roles: list[str] | None = None,
        expires_delta: Optional[timedelta] = None,
    ) -> tuple[str, str]:
        """
        Create a refresh token with a unique token_id for revocation.
        Returns (jwt_string, token_id).
        """
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=settings.refresh_token_expire_days))
        token_id = str(uuid.uuid4())

        payload = {
            **self._base_claims(),
            "sub": str(user_id),
            "tenant_id": tenant_id,
            "roles": roles or [],
            "type": "refresh",
            "token_id": token_id,
            "exp": expire,
        }
        return self._sign(payload), token_id

    def create_api_key_token(
        self,
        user_id: int,
        token_id: str,
        tenant_id: Optional[str] = None,
        permission_ids: list[int] | None = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create a long-lived API key JWT (default 1 year).
        The token_id is stored in DB+Redis; the full JWT is shown once.
        """
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=settings.api_key_expire_days))

        payload = {
            **self._base_claims(),
            "sub": str(user_id),
            "tenant_id": tenant_id,
            "permission_ids": permission_ids or [],
            "type": "api_key",
            "token_id": token_id,
            "exp": expire,
        }
        return self._sign(payload)

    # ── Validation ──

    def validate_token(self, token: str) -> TokenPayload:
        """
        Validate a JWT token with strict checks (RS256 only).

        Verifies: signature, expiry, kid, alg, issuer, audience (if configured).
        Raises TokenInvalidError or TokenExpiredError on failure.
        """
        from app.core.exceptions import TokenExpiredError, TokenInvalidError

        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            alg = header.get("alg")

            if not kid:
                raise TokenInvalidError("Token header missing 'kid'.")
            if alg and alg != "RS256":
                raise TokenInvalidError(f"Unsupported algorithm '{alg}'. Expected RS256.")

            public_key = key_manager.get_public_key(kid)
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )

            decode_kwargs: dict[str, Any] = {
                "algorithms": ["RS256"],
                "options": {"verify_exp": True},
            }
            if settings.jwt_issuer:
                decode_kwargs["issuer"] = settings.jwt_issuer
            if settings.jwt_audience:
                decode_kwargs["audience"] = settings.jwt_audience

            payload = jwt.decode(token, public_pem, **decode_kwargs)

            if not payload.get("sub"):
                raise TokenInvalidError("Token missing 'sub' claim.")
            if not payload.get("type"):
                raise TokenInvalidError("Token missing 'type' claim.")

            return TokenPayload(payload)

        except JWTError as exc:
            if "expired" in str(exc).lower():
                raise TokenExpiredError()
            raise TokenInvalidError(f"Invalid token: {exc}")
        except TokenExpiredError:
            raise
        except TokenInvalidError:
            raise
        except ValueError as exc:
            raise TokenInvalidError(str(exc))

    # ── Internal ──

    def _sign(self, payload: dict[str, Any]) -> str:
        """Sign a payload with the active RS256 private key."""
        private_key = key_manager.get_signing_key()
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return jwt.encode(
            payload,
            private_pem,
            algorithm="RS256",
            headers={"kid": payload["kid"], "alg": "RS256"},
        )
