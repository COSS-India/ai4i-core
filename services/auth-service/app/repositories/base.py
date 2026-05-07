from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, obj: T) -> T:
        self._db.add(obj)
        await self._db.flush()
        return obj

    async def update(self, obj: T, data: dict) -> T:
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        await self._db.flush()
        return obj

    async def refresh(self, obj: T) -> T:
        await self._db.refresh(obj)
        return obj

    async def commit(self) -> None:
        await self._db.commit()

    async def save_and_refresh(self, obj: T) -> T:
        await self._db.commit()
        await self._db.refresh(obj)
        return obj
