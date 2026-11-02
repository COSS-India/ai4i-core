"""user_table_preferences repository: every statement is scoped to one
(user_id, view_key) pair, so one user's selection never touches another's."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.user_preferences import table_preference_repository as repo


def _session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


def _sql(session) -> str:
    stmt = session.execute.call_args.args[0]
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_get_filters_by_user_and_view():
    session = _session()
    await repo.get(session, "user-a", "service-list")
    sql = _sql(session)
    assert "user_table_preferences.user_id = 'user-a'" in sql
    assert "user_table_preferences.view_key = 'service-list'" in sql


@pytest.mark.asyncio
async def test_delete_filters_by_user_and_view():
    session = _session()
    await repo.delete_preference(session, "user-a", "service-list")
    sql = _sql(session)
    assert sql.startswith("DELETE FROM user_table_preferences")
    assert "user_table_preferences.user_id = 'user-a'" in sql
    assert "user_table_preferences.view_key = 'service-list'" in sql
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_conflicts_on_user_and_view_only():
    session = _session()
    await repo.upsert(session, "user-a", "service-list", ["name", "actions", "tier"])
    stmt = session.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (user_id, view_key) DO UPDATE" in sql
    assert "visible_columns = excluded.visible_columns" in sql
    assert "updated_at = now()" in sql
    session.commit.assert_awaited_once()
