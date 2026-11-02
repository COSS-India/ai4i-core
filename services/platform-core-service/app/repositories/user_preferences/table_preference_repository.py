"""Data access for user_table_preferences."""

import uuid
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.user_preferences.table_preference import UserTablePreference


async def get(session: AsyncSession, user_id: str, view_key: str) -> Optional[List[str]]:
    """Stored column ids for the user and view, or None when nothing is stored."""
    result = await session.execute(
        select(UserTablePreference.visible_columns).where(
            UserTablePreference.user_id == user_id,
            UserTablePreference.view_key == view_key,
        )
    )
    return result.scalar_one_or_none()


async def upsert(
    session: AsyncSession, user_id: str, view_key: str, visible_columns: List[str]
) -> None:
    stmt = insert(UserTablePreference).values(
        id=uuid.uuid4(),
        user_id=user_id,
        view_key=view_key,
        visible_columns=visible_columns,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "view_key"],
        set_={"visible_columns": stmt.excluded.visible_columns, "updated_at": func.now()},
    )
    await session.execute(stmt)
    await session.commit()


async def delete_preference(session: AsyncSession, user_id: str, view_key: str) -> None:
    await session.execute(
        delete(UserTablePreference).where(
            UserTablePreference.user_id == user_id,
            UserTablePreference.view_key == view_key,
        )
    )
    await session.commit()
