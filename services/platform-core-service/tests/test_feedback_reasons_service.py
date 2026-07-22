"""Unit tests: FeedbackService.get_reasons — GET /feedback/reasons.

Covers:
  - no taskType filter returns every task type, all 10 task types present
  - every task type's reason list ends with an "other" entry (catalog fallback)
  - taskType filter returns a single-key map, not a bare list
  - a task type with active DB rows is served from the DB instead of the catalog
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.enums.feedback import ModelTaskTypeEnum
from app.schemas.feedback.feedback import Reason
from app.services.feedback.feedback_service import FeedbackService


def _row(task_type: str, code: str, label: str) -> MagicMock:
    return MagicMock(task_type=task_type, code=code, label=label)


def _make_service(rows_by_task_type: dict[str, list] | None = None) -> FeedbackService:
    reason_repo = MagicMock()
    rows_by_task_type = rows_by_task_type or {}

    async def _get_by_task_type_with_language(task_types, lang):
        return [row for t in task_types for row in rows_by_task_type.get(t, [])]

    reason_repo.get_by_task_type_with_language = AsyncMock(
        side_effect=_get_by_task_type_with_language
    )
    return FeedbackService(feedback_repo=MagicMock(), reason_repo=reason_repo)


@pytest.mark.asyncio
async def test_no_task_type_returns_full_catalog():
    svc = _make_service()

    result = await svc.get_reasons(None, lang=None)

    assert set(result.keys()) == {t.value for t in ModelTaskTypeEnum}


@pytest.mark.asyncio
async def test_every_task_type_ends_with_other_reason():
    svc = _make_service()

    result = await svc.get_reasons(None, lang=None)

    for task_type, reasons in result.items():
        assert reasons[-1].code == "other", f"{task_type} missing trailing 'other' reason"


@pytest.mark.asyncio
async def test_task_type_filter_returns_single_key_map():
    svc = _make_service()

    result = await svc.get_reasons([ModelTaskTypeEnum.ASR], lang=None)

    assert set(result.keys()) == {"ASR"}
    codes = [r.code for r in result["ASR"]]
    assert codes == ["missing_words", "wrong_language_detected", "other"]


@pytest.mark.asyncio
async def test_task_type_with_active_db_rows_is_served_from_db():
    svc = _make_service({"asr": [_row("asr", "names", "Names")]})

    result = await svc.get_reasons([ModelTaskTypeEnum.ASR], lang=None)

    assert result == {"ASR": [Reason(code="names", label="Names")]}


@pytest.mark.asyncio
async def test_lang_selects_translation_from_db_row_label():
    """The repository resolves label_i18n[lang] at the DB level, so the
    service just needs to pass lang through and use row.label verbatim."""
    svc = _make_service({"asr": [_row("asr", "names", "नाम")]})

    result = await svc.get_reasons([ModelTaskTypeEnum.ASR], lang="hi")

    assert result["ASR"][0].label == "नाम"


@pytest.mark.asyncio
async def test_task_type_with_no_active_db_rows_falls_back_to_catalog():
    svc = _make_service({"asr": []})

    result = await svc.get_reasons([ModelTaskTypeEnum.ASR], lang=None)

    codes = [r.code for r in result["ASR"]]
    assert codes == ["missing_words", "wrong_language_detected", "other"]


@pytest.mark.asyncio
async def test_no_task_type_mixes_db_rows_and_catalog_fallback():
    """asr comes from the DB (one query for all task types), everything
    else falls back to the static catalog since no rows were seeded."""
    svc = _make_service({"asr": [_row("asr", "names", "Names")]})

    result = await svc.get_reasons(None, lang=None)

    assert result["ASR"] == [Reason(code="names", label="Names")]
    assert [r.code for r in result["NMT"]] == [
        "incorrect_meaning",
        "missing_translation",
        "other",
    ]


@pytest.mark.asyncio
async def test_multiple_task_types_returns_map_for_all_requested():
    svc = _make_service({"asr": [_row("asr", "names", "Names")]})

    result = await svc.get_reasons(
        [ModelTaskTypeEnum.ASR, ModelTaskTypeEnum.TTS], lang=None
    )

    assert set(result.keys()) == {"ASR", "TTS"}
    assert result["ASR"] == [Reason(code="names", label="Names")]
    assert [r.code for r in result["TTS"]] == [
        "unnatural_voice",
        "wrong_pronunciation",
        "audio_quality_issue",
        "other",
    ]