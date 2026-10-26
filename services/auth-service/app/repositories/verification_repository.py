"""
TokenVerification table queries — used for email activation setup links.

The token_verification table has no user_id FK column. User identity is
embedded in the signed JWT token string itself, and created_by stores
the user UUID string to allow bulk-deactivation on resend. Token type
is also embedded in the JWT payload, not stored as a column.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
from jwt.exceptions import PyJWTError
from cryptography.hazmat.primitives import serialization

from app.models.verification import TokenVerification
from app.repositories.base import BaseRepository
from app.core.constants import TokenType
from app.core.security import key_manager

logger = logging.getLogger(__name__)


def _decode_stored_token(token: str, kid: str) -> dict:
    """RS256 signature-verified decode of a stored token. ``verify_exp=False``:
    callers filter or deliberately include expired rows themselves. Raises
    PyJWTError / ValueError (unknown kid) on failure."""
    public_key = key_manager.get_public_key(kid)
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return jwt.decode(
        token,
        public_pem,
        algorithms=["RS256"],
        options={"verify_exp": False},
    )


class VerificationRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def _live_email_change_tokens(self) -> list[tuple[TokenVerification, dict]]:
        """Active, unexpired EMAIL_CHANGE rows with their verified claims.

        Token type and tenant live only in the signed JWT (no columns), so this
        decodes every live row. That set is small: only links issued in the
        last ``setup_token_expire_hours`` that haven't been used. Unverifiable
        rows are skipped.
        """
        result = await self._db.execute(
            select(TokenVerification)
            .where(
                TokenVerification.is_active == True,  # noqa: E712
                TokenVerification.expires_at > datetime.now(timezone.utc),
            )
            .order_by(TokenVerification.id)
        )
        live: list[tuple[TokenVerification, dict]] = []
        for token_obj in result.scalars().all():
            try:
                kid = jwt.get_unverified_header(token_obj.token).get("kid")  # NOSONAR(python:S5659)
                if not kid:
                    continue
                payload = _decode_stored_token(token_obj.token, kid)
            except (PyJWTError, ValueError) as e:
                logger.warning(
                    "Skipping unverifiable token for user %s: %s", token_obj.created_by, e
                )
                continue
            if payload.get("type") == TokenType.EMAIL_CHANGE:
                live.append((token_obj, payload))
        return live

    async def get_pending_email_changes(self, tenant_ids: list[int]) -> dict[int, str]:
        """Map tenant id → new email awaiting verification. A new request
        supersedes the previous one, so there is at most one per tenant."""
        if not tenant_ids:
            return {}
        wanted = {str(t) for t in tenant_ids}
        return {
            int(payload["tenant_id"]): payload["email"]
            for _, payload in await self._live_email_change_tokens()
            if payload.get("tenant_id") in wanted and payload.get("email")
        }

    async def deactivate_email_changes_for_tenant(self, tenant_id: int) -> None:
        """Invalidate any outstanding EMAIL_CHANGE link for this tenant — called
        whenever its email changes or a newer change is requested."""
        for token_obj, payload in await self._live_email_change_tokens():
            if payload.get("tenant_id") == str(tenant_id):
                token_obj.is_active = False
        await self._db.flush()

    async def get_by_token(self, token: str) -> Optional[TokenVerification]:
        result = await self._db.execute(
            select(TokenVerification).where(TokenVerification.token == token)
        )
        return result.scalar_one_or_none()

    async def deactivate(self, token_obj: TokenVerification) -> None:
        token_obj.is_active = False
        await self._db.flush()

    async def deactivate_all_for_user(self, user_uuid: str, token_type: Optional[str] = None) -> None:
        """Mark all active tokens for a user as inactive before issuing a new one.

        If token_type is provided, only deactivate tokens of that type.
        Token type is decoded from the JWT payload, not stored as a column.
        """
        result = await self._db.execute(
            select(TokenVerification).where(
                TokenVerification.created_by == user_uuid,
                TokenVerification.is_active == True,  # noqa: E712
            )
        )
        for token_obj in result.scalars().all():
            if token_type is None:
                token_obj.is_active = False
            else:
                # RS256 signature-verified read of the ``type`` claim. Why
                # full verification matters even though these rows come from
                # our own DB: it makes signature tampering on stored tokens
                # detectable here too, and silences python:S5659 which (
                # correctly) flags any payload read that skips verification.
                #
                # ``verify_exp=False`` is deliberate: this method is called
                # specifically to deactivate stale tokens, many of which have
                # already expired. Refusing expired tokens here would leave
                # them flagged as ``is_active=true`` forever.
                try:
                    header = jwt.get_unverified_header(token_obj.token)  # NOSONAR(python:S5659)
                    kid = header.get("kid")
                    if not kid:
                        # No kid → cannot verify, but also no way to scope
                        # by token type. Preserve the pre-S5659 deactivation
                        # coverage and fail closed: invalidate a token we
                        # cannot trust rather than leave it live.
                        logger.warning(
                            "Deactivating kid-less token for user %s — "
                            "cannot verify, safer to invalidate",
                            user_uuid,
                        )
                        token_obj.is_active = False
                        continue
                    payload = _decode_stored_token(token_obj.token, kid)
                    # JWT claim name is ``type`` (see TokenService._create_token);
                    # the older `payload.get("token_type")` here always returned
                    # None, so token-type-scoped deactivation was a silent no-op.
                    if payload.get("type") == token_type:
                        token_obj.is_active = False
                except (PyJWTError, ValueError) as e:
                    # Unknown kid → ValueError from key_manager; bad signature
                    # → JWTError. Either way, leave the row alone (safest).
                    logger.warning(
                        "Failed to verify token for user %s: %s", user_uuid, e
                    )
        await self._db.flush()
