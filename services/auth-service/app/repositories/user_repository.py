"""
User table queries.
"""

import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import Text, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import USERNAME_MAX_LENGTH
from app.models.credentials import UserCredentials
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self._db.execute(
            select(User).where(User.id == user_id, User.is_delete.isnot(True))
        )
        return result.scalar_one_or_none()

    async def is_active(self, user_id: UUID) -> bool:
        """Lightweight check: is user active? (no full object fetch)."""
        result = await self._db.execute(
            select(User.is_active).where(User.id == user_id, User.is_delete.isnot(True))
        )
        is_active = result.scalar_one_or_none()
        return is_active is True

    async def get_by_email(self, email: str) -> Optional[User]:
        # Match either storage form so seeded/legacy plaintext rows (e.g. the
        # default admin/guest accounts inserted without encryption) keep working
        # alongside encrypted rows:
        #   * ``User.email == email`` encrypts the parameter via the column's
        #     bind processor, matching deterministic-ciphertext rows.
        #   * ``cast(User.email, Text) == <normalised>`` compares the raw stored
        #     value as plain text (bypassing the encrypting bind processor),
        #     matching un-encrypted rows exactly as before.
        result = await self._db.execute(
            select(User).where(
                or_(
                    User.email == email,
                    cast(User.email, Text) == email.strip().lower(),
                ),
                User.is_delete.isnot(True),
            )
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Return True if any user (including soft-deleted) has this email."""
        result = await self._db.execute(
            select(User.id).where(
                or_(
                    User.email == email,
                    cast(User.email, Text) == email.strip().lower(),
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self._db.execute(
            select(User).where(User.username == username, User.is_delete.isnot(True))
        )
        return result.scalar_one_or_none()

    async def list_usernames_in_collision_family(self, base: str) -> list[str]:
        """Usernames equal to ``base`` or ``base_<digits>`` (one query, not per-suffix)."""
        base = base[:USERNAME_MAX_LENGTH]
        family_re = re.compile(rf"^{re.escape(base)}(_\d+)?$")
        escaped_like = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        result = await self._db.execute(
            select(User.username).where(
                User.is_delete.isnot(True),
                or_(
                    User.username == base,
                    User.username.like(f"{escaped_like}\\_%", escape="\\"),
                ),
            )
        )
        return [name for name in result.scalars().all() if family_re.match(name)]

    async def list_all(self, offset: int = 0, limit: int = 100) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.is_delete.isnot(True))
            .order_by(func.lower(User.username).asc(), User.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_tenant(self, tenant_id: int, offset: int = 0, limit: int = 100) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.tenant_id == tenant_id, User.is_delete.isnot(True))
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def lock_tenant_users_for_status(
        self,
        tenant_id: int,
        *,
        updated_by: Optional[UUID] = None,
    ) -> None:
        """When tenant is SUSPENDED/DEACTIVATED: clear tenant access only (``is_tenant_active``).

        Only users who have completed setup (a credentials row exists) are
        locked. Pending-activation users never had an active account, so
        marking them Suspended would be semantically wrong and could strand
        them if the flag is not restored on reactivation; they keep
        ``is_tenant_active`` untouched and stay Pending Activation.
        """
        values: dict = {"is_tenant_active": False}
        if updated_by is not None:
            values["updated_by"] = updated_by
        has_credentials = (
            select(UserCredentials.id)
            .where(UserCredentials.user_id == User.id)
            .exists()
        )
        await self._db.execute(
            update(User)
            .where(
                User.tenant_id == tenant_id,
                User.is_delete.isnot(True),
                has_credentials,
            )
            .values(**values)
        )
        await self._db.flush()

    async def unlock_tenant_users_for_status(
        self,
        tenant_id: int,
        *,
        updated_by: Optional[UUID] = None,
    ) -> None:
        """When tenant becomes ACTIVE: restore tenant access (``is_tenant_active``) for all users."""
        values: dict = {"is_tenant_active": True}
        if updated_by is not None:
            values["updated_by"] = updated_by
        await self._db.execute(
            update(User)
            .where(User.tenant_id == tenant_id, User.is_delete.isnot(True))
            .values(**values)
        )
        await self._db.flush()
