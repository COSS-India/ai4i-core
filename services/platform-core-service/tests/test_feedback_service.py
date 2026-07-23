"""Unit tests: FeedbackService.submit — thumbs up/down, v0.1.

Covers the rules from the Explicit Feedback API LLD:
  - negative-only detail (reasons/comments/correctedOutput rejected on POSITIVE)
  - modelTaskType canonicalisation to the internal TaskTypeEnum vocabulary
  - anonymous/guest tenant handling (tenant_id null -> feedback_source PORTAL_TRY_IT_NOW)
  - upsert-by-request_id delegated to the repository
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.schemas.enums.feedback import FeedbackTypeEnum, ModelTaskTypeEnum, RatingEnum
from app.schemas.feedback.feedback import FeedbackSubmission, LanguageInfo
from app.services.feedback.feedback_service import FeedbackService, FeedbackValidationError


def _make_service(saved_id: UUID | None = None):
    repo = MagicMock()
    repo.create_or_update = AsyncMock(
        side_effect=lambda entity: _stamp(entity, saved_id or uuid4())
    )
    return FeedbackService(feedback_repo=repo, reason_repo=MagicMock()), repo


def _stamp(entity, id_):
    """create_or_update normally returns the persisted row (with its id
    resolved) — stub that behaviour without a real DB."""
    entity.id = id_
    return entity


def _submission(**overrides) -> FeedbackSubmission:
    defaults = dict(
        requestId=uuid4(),
        modelTaskType=ModelTaskTypeEnum.NMT,
        feedbackType=FeedbackTypeEnum.THUMBS,
        rating=RatingEnum.POSITIVE,
        modelProvider="AI4Bharat",
        modelVersion="v2",
    )
    defaults.update(overrides)
    return FeedbackSubmission(**defaults)


@pytest.mark.asyncio
async def test_thumbs_up_has_no_detail_fields():
    svc, repo = _make_service()
    payload = _submission(rating=RatingEnum.POSITIVE)

    result = await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    assert result.status == "SUCCESS"
    saved_entity = repo.create_or_update.call_args.args[0]
    assert saved_entity.rating == RatingEnum.POSITIVE
    assert saved_entity.reasons is None
    assert saved_entity.comments is None
    assert saved_entity.corrected_output is None


@pytest.mark.asyncio
async def test_thumbs_down_persists_reasons_and_comments():
    svc, repo = _make_service()
    payload = _submission(
        rating=RatingEnum.NEGATIVE,
        reasons=["incorrect_meaning", "wrong_terminology"],
        comments="translation dropped the negation",
    )

    await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    saved_entity = repo.create_or_update.call_args.args[0]
    assert saved_entity.reasons == ["incorrect_meaning", "wrong_terminology"]
    assert saved_entity.comments == "translation dropped the negation"


@pytest.mark.asyncio
async def test_positive_rating_with_reasons_is_rejected():
    svc, _repo = _make_service()
    payload = _submission(rating=RatingEnum.POSITIVE, reasons=["incorrect_meaning"])

    with pytest.raises(FeedbackValidationError) as exc_info:
        await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_anonymous_submission_has_null_tenant_and_portal_source():
    svc, repo = _make_service()
    payload = _submission()

    await svc.submit(payload, tenant_id=None, created_by=None)

    saved_entity = repo.create_or_update.call_args.args[0]
    assert saved_entity.tenant_id is None
    assert saved_entity.feedback_source == "PORTAL_TRY_IT_NOW"
    assert saved_entity.created_by is None


@pytest.mark.asyncio
async def test_tenant_submission_has_api_source():
    svc, repo = _make_service()
    payload = _submission()

    await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    saved_entity = repo.create_or_update.call_args.args[0]
    assert saved_entity.tenant_id == "tenant-1"
    assert saved_entity.feedback_source == "API"


@pytest.mark.asyncio
async def test_model_task_type_is_canonicalised():
    """TEXT_LANG_DETECTION (Feedback API vocabulary) must be stored as the
    platform's internal 'language-detection' (TaskTypeEnum vocabulary)."""
    svc, repo = _make_service()
    payload = _submission(modelTaskType=ModelTaskTypeEnum.TEXT_LANG_DETECTION)

    await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    saved_entity = repo.create_or_update.call_args.args[0]
    assert saved_entity.model_task_type == "language-detection"


@pytest.mark.asyncio
async def test_single_pair_language_info_is_split_into_columns():
    svc, repo = _make_service()
    payload = _submission(
        modelTaskType=ModelTaskTypeEnum.NMT,
        languageInfo=[LanguageInfo(sourceLanguage="or", targetLanguage="en")],
    )

    await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    saved_entity = repo.create_or_update.call_args.args[0]
    assert saved_entity.source_language == "or"
    assert saved_entity.target_language == "en"
    assert saved_entity.language_info == [{"sourceLanguage": "or", "targetLanguage": "en"}]


@pytest.mark.asyncio
async def test_multi_pair_language_info_preserves_full_list():
    """A bidirectional model's full model.language capability (both
    directions) must be preserved verbatim in language_info, with
    source_language/target_language best-effort from the first pair."""
    svc, repo = _make_service()
    payload = _submission(
        modelTaskType=ModelTaskTypeEnum.NMT,
        languageInfo=[
            LanguageInfo(sourceLanguage="en", targetLanguage="hi"),
            LanguageInfo(sourceLanguage="hi", targetLanguage="en"),
        ],
    )

    await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    saved_entity = repo.create_or_update.call_args.args[0]
    assert saved_entity.source_language == "en"
    assert saved_entity.target_language == "hi"
    assert saved_entity.language_info == [
        {"sourceLanguage": "en", "targetLanguage": "hi"},
        {"sourceLanguage": "hi", "targetLanguage": "en"},
    ]


@pytest.mark.asyncio
async def test_no_language_info_stores_none():
    svc, repo = _make_service()
    payload = _submission(modelTaskType=ModelTaskTypeEnum.SPEAKER_DIARIZATION)

    await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    saved_entity = repo.create_or_update.call_args.args[0]
    assert saved_entity.source_language is None
    assert saved_entity.target_language is None
    assert saved_entity.language_info is None


@pytest.mark.asyncio
async def test_response_shape_matches_spec():
    fixed_id = uuid4()
    svc, _repo = _make_service(saved_id=fixed_id)
    payload = _submission()

    result = await svc.submit(payload, tenant_id="tenant-1", created_by="user-1")

    assert result.status == "SUCCESS"
    assert result.feedbackId == fixed_id
    assert result.message == "Feedback recorded successfully."
