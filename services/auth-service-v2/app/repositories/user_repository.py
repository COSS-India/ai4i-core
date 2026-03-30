"""
User table queries.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self._db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self._db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self._db.add(user)
        await self._db.flush()
        return user

    async def update(self, user: User, data: dict) -> User:
        for key, value in data.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        await self._db.flush()
        return user

    async def update_last_login(self, user: User) -> None:
        user.last_login = datetime.now(timezone.utc)
        await self._db.flush()

    async def update_password(self, user: User, password_hash: str, salt: str, rounds: int) -> None:
        user.password_hash = password_hash
        user.password_salt = salt
        user.hash_rounds = rounds
        await self._db.flush()

    async def list_all(self, offset: int = 0, limit: int = 100) -> list[User]:
        result = await self._db.execute(
            select(User).order_by(User.id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_tenant(self, tenant_id: str, offset: int = 0, limit: int = 100) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.tenant_id_cached == tenant_id)
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._db.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def commit(self) -> None:
        await self._db.commit()
