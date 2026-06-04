"""
JWT token creation and validation (RS256 only).

Token contract:
- Access tokens:  sub, tenant_id, permission_ids, type=access_token — no roles, no token_id
- Refresh tokens: sub, tenant_id, type=refresh — no roles, no token_id
- API key tokens: sub, tenant_id, permission_ids, type=api_key, token_id (for revocation)
- Setup tokens:   sub, email, type=setup (for email activation)
All tokens include: iss, iat, kid, alg=RS256
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import jwt, JWTError, ExpiredSignatureError
from cryptography.hazmat.primitives import serialization

from app.core.config import settings
from app.core.constants import TokenType
from app.core.exceptions import TokenExpiredError, TokenInvalidError
from app.core.security import key_manager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT payload — only the claims auth-service actually reads.

    Other JWT claims (tenant_id, permission_ids, email, exp, iss, aud, kid)
    are still verified by the JWTVerifier (sig/exp/iss/aud/alg/kid checks)
    but they're not surfaced here because no consumer reads them off
    TokenPayload — callers either work from AuthClaims directly (validate
    flow) or only need sub/token_id/token_type (provision/setup flows).

    Frozen: post-creation mutation is forbidden to ensure auth claims immutability.
    """

    sub: str
    token_type: str
    token_id: Optional[str] = None
    tenant_id: Optional[str] = None


class TokenService:
    """Creates and validates RS256 JWT tokens with strict iss/aud/alg/kid claims."""

    def _create_token(
        self,
        token_type: str,
        sub: str,
        extra: dict[str, Any],
        default_delta: timedelta,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Template method for token creation. All token types follow: expire + payload + sign."""
        expire = datetime.now(timezone.utc) + (expires_delta or default_delta)
        payload = {**self._base_claims(), "sub": sub, "type": token_type, "exp": expire, **extra}
        return self._sign(payload)

    def _base_claims(self) -> dict[str, Any]:
        # `jti` makes every token unique even when (sub, type, iat) collide —
        # `iat` has only 1-second precision, so without a nonce two
        # verify/setup/reset tokens issued in the same second produce
        # identical JWT bytes and collide on token_verification.token UNIQUE.
        claims: dict[str, Any] = {
            "iss": settings.jwt_issuer,
            "iat": datetime.now(timezone.utc),
            "jti": uuid.uuid4().hex,
            "kid": key_manager.get_signing_kid(),
        }
        if settings.jwt_audience:
            claims["aud"] = settings.jwt_audience
        return claims

    # ── Creation ──

    def create_access_token(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        permission_ids: list[int] | None = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Short-lived access token. Contains permission_ids only — no roles."""
        return self._create_token(
            token_type=TokenType.ACCESS,
            sub=str(user_id),
            extra={"tenant_id": tenant_id, "permission_ids": permission_ids or []},
            default_delta=timedelta(minutes=settings.access_token_expire_minutes),
            expires_delta=expires_delta,
        )

    def create_refresh_token(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Refresh token. No roles, no token_id — revocation is via DB row deletion."""
        return self._create_token(
            token_type=TokenType.REFRESH,
            sub=str(user_id),
            extra={"tenant_id": tenant_id},
            default_delta=timedelta(days=settings.refresh_token_expire_days),
            expires_delta=expires_delta,
        )

    def create_setup_token(
        self,
        user_id: str,
        email: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Short-lived email activation token. Signed JWT, stored in token_verification table."""
        return self._create_token(
            token_type=TokenType.SETUP,
            sub=str(user_id),
            extra={"email": email},
            default_delta=timedelta(hours=settings.setup_token_expire_hours),
            expires_delta=expires_delta,
        )

    def create_reset_token(
        self,
        user_id: str,
        email: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Short-lived password-reset token. 30-min default per security spec —
        much shorter than SETUP/VERIFY (48h) since reset is initiated by an
        already-active user and the link is sensitive."""
        return self._create_token(
            token_type=TokenType.RESET,
            sub=str(user_id),
            extra={"email": email},
            default_delta=timedelta(minutes=settings.reset_token_expire_minutes),
            expires_delta=expires_delta,
        )

    def create_verify_token(
        self,
        user_id: str,
        email: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Short-lived email-verification token. Signed JWT, stored in
        token_verification table. Distinct from SETUP: VERIFY only flips
        is_active=True (the user already supplied a password at signup).
        """
        return self._create_token(
            token_type=TokenType.VERIFY,
            sub=str(user_id),
            extra={"email": email},
            default_delta=timedelta(hours=settings.setup_token_expire_hours),
            expires_delta=expires_delta,
        )

    # ── Validation ──

    def validate_token(self, token: str) -> TokenPayload:
        """
        Validate a JWT token (RS256 only).
        Verifies: signature, expiry, kid, alg, issuer, audience (if configured).
        Raises TokenInvalidError or TokenExpiredError on failure.
        """
        # Header-only read to pick the right public key by ``kid`` before
        # signature verification. The signature is verified below by
        # ``jwt.decode(token, public_pem, algorithms=["RS256"], ...)``. This
        # is the JWKS kid-selection pattern that python:S5659 itself
        # recommends — see the rule's own note about ``get_unverified_header``.
        try:
            header = jwt.get_unverified_header(token)  # NOSONAR
            kid = header.get("kid")
            alg = header.get("alg")

            if not kid:
                raise TokenInvalidError("Token header missing 'kid'.")
            if alg != "RS256":
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

            return TokenPayload(
                sub=str(payload.get("sub", "")),
                token_type=payload.get("type", ""),
                token_id=payload.get("token_id"),
                tenant_id=payload.get("tenant_id"),
            )

        except ExpiredSignatureError as exc:
            raise TokenExpiredError() from exc
        except JWTError as exc:
            raise TokenInvalidError("Token validation failed.") from exc
        except TokenExpiredError:
            raise
        except TokenInvalidError:
            raise
        except ValueError as exc:
            raise TokenInvalidError("Token validation failed.") from exc

    # ── Internal ──

    def _sign(self, payload: dict[str, Any]) -> str:
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
