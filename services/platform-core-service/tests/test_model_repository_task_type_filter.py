"""Regression coverage for ModelRepository/ServiceRepository's task_types
filter being case-insensitive (PR #1506 review comment) — an exact JSONB
match against mm_models.task["type"] would silently ghost/exclude a row
stored with different casing than the caller's task_types list, while
/api/v1/models' TaskSpecLenient still renders that same row normally. This
only ever ran with task_types=["llm"] before model_breakdown was
generalized to every task type, so a casing mismatch could never surface
until now.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.model_management.model_repository import ModelRepository
from app.repositories.model_management.service_repository import ServiceRepository

pytestmark = pytest.mark.asyncio


def _db_capturing_stmt():
    """A fake AsyncSession whose execute() records the statement it was
    given and returns an empty result — enough to inspect the compiled SQL
    without a real database."""
    db = MagicMock()
    captured = {}

    async def fake_execute(stmt):
        captured["stmt"] = stmt
        result = MagicMock()
        result.scalar.return_value = 0
        result.all.return_value = []
        return result

    db.execute = AsyncMock(side_effect=fake_execute)
    return db, captured


def _compiled_sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestModelRepositoryTaskTypeFilterCaseInsensitive:
    async def test_count_models_lowercases_the_task_type_filter(self):
        db, captured = _db_capturing_stmt()
        repo = ModelRepository(db)

        await repo.count_models(task_types=["NMT", "Audio-Lang-Detection"])

        sql = _compiled_sql(captured["stmt"])
        assert "lower(" in sql
        assert "'nmt'" in sql
        assert "'audio-lang-detection'" in sql
        # The mixed-case values as given by the caller must NOT appear
        # un-lowered on the right-hand side of the filter.
        assert "'NMT'" not in sql
        assert "'Audio-Lang-Detection'" not in sql

    async def test_get_model_names_lowercases_the_task_type_filter(self):
        db, captured = _db_capturing_stmt()
        repo = ModelRepository(db)

        await repo.get_model_names(["hash-1"], task_types=["NER"])

        sql = _compiled_sql(captured["stmt"])
        assert "lower(" in sql
        assert "'ner'" in sql
        assert "'NER'" not in sql

    async def test_list_models_lowercases_the_task_type_filter(self):
        db, captured = _db_capturing_stmt()
        repo = ModelRepository(db)

        await repo.list_models(task_types=["OCR"])

        sql = _compiled_sql(captured["stmt"])
        assert "lower(" in sql
        assert "'ocr'" in sql
        assert "'OCR'" not in sql


class TestServiceRepositoryTaskTypeFilterCaseInsensitive:
    async def test_count_services_lowercases_the_task_type_filter(self):
        db, captured = _db_capturing_stmt()
        repo = ServiceRepository(db)

        await repo.count_services(task_types=["ASR"])

        sql = _compiled_sql(captured["stmt"])
        assert "lower(" in sql
        assert "'asr'" in sql
        assert "'ASR'" not in sql

    async def test_list_services_lowercases_the_task_type_filter(self):
        db, captured = _db_capturing_stmt()
        repo = ServiceRepository(db)

        await repo.list_services(task_types=["TTS"])

        sql = _compiled_sql(captured["stmt"])
        assert "lower(" in sql
        assert "'tts'" in sql
        assert "'TTS'" not in sql
