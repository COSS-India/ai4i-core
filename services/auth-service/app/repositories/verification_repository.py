"""
TokenVerification table queries — used for email activation setup links.

The token_verification table has no user_id FK column. User identity is
embedded in the signed JWT token string itself, and created_by stores
the user UUID string to allow bulk-deactivation on resend. Token type
is also embedded in the JWT payload, not stored as a column.
"""

import logging
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


class VerificationRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

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
                    public_key = key_manager.get_public_key(kid)
                    public_pem = public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    payload = jwt.decode(
                        token_obj.token,
                        public_pem,
                        algorithms=["RS256"],
                        options={"verify_exp": False},
                    )
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
