"""Unit tests: FeedbackRepository.create_or_update.

Regression: entity.id relied on the ORM column's default=uuid.uuid4, which
only applies when SQLAlchemy issues the INSERT via session.add()+flush.
This repository builds a raw Core insert()/ON CONFLICT statement instead,
reading entity.id as a plain attribute — so the column default never fired
and every insert violated the NOT NULL constraint on id. The fix generates
id explicitly in create_or_update before building the statement.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.models.feedback.feedback import Feedback
from app.repositories.feedback.feedback_repository import FeedbackRepository


def _make_repo():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    repo = FeedbackRepository(db)
    return repo, db


def _make_entity(id_=None) -> Feedback:
    return Feedback(
        id=id_,
        request_id=uuid4(),
        model_task_type="nmt",
        feedback_type="THUMBS",
        rating="POSITIVE",
        model_provider="AI4Bharat",
        model_version="v2",
    )


@pytest.mark.asyncio
async def test_create_or_update_generates_id_when_absent(monkeypatch):
    repo, db = _make_repo()
    repo.get_by_request_id = AsyncMock(return_value="persisted-row")
    entity = _make_entity(id_=None)

    await repo.create_or_update(entity)

    # entity.id must be a real UUID by the time the INSERT is built — never
    # left None for the raw Core statement to send to Postgres.
    assert isinstance(entity.id, UUID)
    db.execute.assert_awaited_once()

    insert_stmt = db.execute.call_args.args[0]
    compiled_params = insert_stmt.compile().params
    assert compiled_params["id"] == entity.id
    assert compiled_params["id"] is not None


@pytest.mark.asyncio
async def test_create_or_update_preserves_existing_id():
    repo, db = _make_repo()
    repo.get_by_request_id = AsyncMock(return_value="persisted-row")
    fixed_id = uuid4()
    entity = _make_entity(id_=fixed_id)

    await repo.create_or_update(entity)

    assert entity.id == fixed_id


@pytest.mark.asyncio
async def test_create_or_update_does_not_overwrite_id_on_conflict():
    """id/request_id must be excluded from the ON CONFLICT DO UPDATE SET
    clause — a resubmission must keep the original row's identity."""
    repo, db = _make_repo()
    repo.get_by_request_id = AsyncMock(return_value="persisted-row")
    entity = _make_entity(id_=None)

    await repo.create_or_update(entity)

    insert_stmt = db.execute.call_args.args[0]
    set_clause_keys = {
        col.name if hasattr(col, "name") else col
        for col, _value in insert_stmt._post_values_clause.update_values_to_set
    }
    assert "id" not in set_clause_keys
    assert "request_id" not in set_clause_keys
