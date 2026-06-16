from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")

# Fields that must never be overwritten via update() — PKs, audit fields, SQLAlchemy internals
_IMMUTABLE_FIELDS = frozenset({"id", "created_at", "created_by", "_sa_instance_state"})


class BaseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, obj: T) -> T:
        self._db.add(obj)
        await self._db.flush()
        return obj

    async def update(self, obj: T, data: dict) -> T:
        for key, value in data.items():
            if key not in _IMMUTABLE_FIELDS and hasattr(obj, key):
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
