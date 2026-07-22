"""Unit tests: FeedbackService.get_reasons — GET /feedback/reasons stub (v0.1).

Covers:
  - no taskType filter returns the full catalog, all 10 task types present
  - every task type's reason list ends with an "other" entry
  - taskType filter returns a single-key map, not a bare list
"""

from unittest.mock import MagicMock

from app.schemas.enums.feedback import ModelTaskTypeEnum
from app.services.feedback.feedback_service import FeedbackService


def _make_service() -> FeedbackService:
    return FeedbackService(feedback_repo=MagicMock())


def test_no_task_type_returns_full_catalog():
    svc = _make_service()

    result = svc.get_reasons(None)

    assert set(result.keys()) == {t.value for t in ModelTaskTypeEnum}


def test_every_task_type_ends_with_other_reason():
    svc = _make_service()

    result = svc.get_reasons(None)

    for task_type, reasons in result.items():
        assert reasons[-1].code == "other", f"{task_type} missing trailing 'other' reason"


def test_task_type_filter_returns_single_key_map():
    svc = _make_service()

    result = svc.get_reasons(ModelTaskTypeEnum.ASR)

    assert set(result.keys()) == {"ASR"}
    codes = [r.code for r in result["ASR"]]
    assert codes == ["missing_words", "wrong_language_detected", "other"]