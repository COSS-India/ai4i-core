from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, obj):
        self._db.add(obj)
        await self._db.flush()
        return obj

    async def update(self, obj, data: dict):
        for key, value in data.items():
            if hasattr(obj, key) and value is not None:
                setattr(obj, key, value)
        await self._db.flush()
        return obj

    async def refresh(self, obj):
        await self._db.refresh(obj)
        return obj

    async def commit(self) -> None:
        await self._db.commit()

    async def save_and_refresh(self, obj):
        await self._db.commit()
        await self._db.refresh(obj)
        return obj
