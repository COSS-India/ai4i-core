"""Unit tests for TransliterationTaskService — validate_request constraints and
derived field injection (is_word_level, top_k)."""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.asyncio


def _payload(*, src="hi", tgt="en", num_suggestions=0, is_sentence=False, source="namaste"):
    return {
        "input": [{"source": source}],
        "config": {
            "language": {"sourceLanguage": src, "targetLanguage": tgt},
            "numSuggestions": num_suggestions,
            "isSentence": is_sentence,
        },
    }


# ── numSuggestions + isSentence constraint ────────────────────────────────────

async def test_validate_rejects_numSuggestions_with_isSentence(transliteration_service):
    with pytest.raises(ValueError, match="not valid for sentence-level"):
        await transliteration_service.validate_request(
            _payload(num_suggestions=3, is_sentence=True)
        )


async def test_validate_accepts_suggestions_in_word_mode(transliteration_service):
    payload = _payload(num_suggestions=5, is_sentence=False)
    await transliteration_service.validate_request(payload)
    assert payload["config"]["top_k"] == 5
    assert payload["config"]["is_word_level"] is True


async def test_validate_accepts_sentence_mode_without_suggestions(transliteration_service):
    payload = _payload(num_suggestions=0, is_sentence=True)
    await transliteration_service.validate_request(payload)
    assert payload["config"]["is_word_level"] is False


# ── language validation ───────────────────────────────────────────────────────

async def test_validate_rejects_missing_target_language(transliteration_service):
    payload = {
        "input": [{"source": "namaste"}],
        "config": {"language": {"sourceLanguage": "hi"}},
    }
    with pytest.raises(ValueError, match="target_language is required"):
        await transliteration_service.validate_request(payload)


async def test_validate_rejects_same_source_and_target_language(transliteration_service):
    with pytest.raises(ValueError, match="cannot be the same"):
        await transliteration_service.validate_request(_payload(src="hi", tgt="hi"))


async def test_validate_accepts_valid_language_pair(transliteration_service):
    payload = _payload(src="hi", tgt="en")
    await transliteration_service.validate_request(payload)


# ── derived field injection ───────────────────────────────────────────────────

async def test_validate_injects_is_word_level_and_top_k(transliteration_service):
    payload = _payload(num_suggestions=3, is_sentence=False)
    await transliteration_service.validate_request(payload)
    assert payload["config"]["is_word_level"] is True
    assert payload["config"]["top_k"] == 3


async def test_validate_injects_top_k_zero_when_no_suggestions(transliteration_service):
    payload = _payload(num_suggestions=0, is_sentence=False)
    await transliteration_service.validate_request(payload)
    assert payload["config"]["top_k"] == 0


# ── postprocess_output — ULCA SentencesList grouping ─────────────────────────

async def test_groups_suggestion_rows_into_single_item_with_target_array(transliteration_service):
    from services.base.task_service import PostProcessFormat

    result = PostProcessFormat(
        payload={"config": {"top_k": 3}},
        response_data=[{"target": "a"}, {"target": "b"}, {"target": "c"}],
        source_texts=["namaste"],
    )
    response = await transliteration_service.postprocess_output(result)
    assert response == {"output": [{"source": "namaste", "target": ["a", "b", "c"]}]}


async def test_sentence_mode_still_wraps_single_result_in_a_list(transliteration_service):
    from services.base.task_service import PostProcessFormat

    result = PostProcessFormat(
        payload={"config": {"top_k": 0}},
        response_data=[{"target": "translit sentence"}],
        source_texts=["some sentence"],
    )
    response = await transliteration_service.postprocess_output(result)
    assert response == {"output": [{"source": "some sentence", "target": ["translit sentence"]}]}


async def test_multiple_inputs_each_get_their_own_suggestion_bucket(transliteration_service):
    from services.base.task_service import PostProcessFormat

    result = PostProcessFormat(
        payload={"config": {"top_k": 2}},
        response_data=[{"target": "a1"}, {"target": "a2"}, {"target": "b1"}, {"target": "b2"}],
        source_texts=["wordA", "wordB"],
    )
    response = await transliteration_service.postprocess_output(result)
    assert response == {"output": [
        {"source": "wordA", "target": ["a1", "a2"]},
        {"source": "wordB", "target": ["b1", "b2"]},
    ]}


async def test_handles_short_row_count_without_raising(transliteration_service):
    """Fewer rows than sources*rows_per_item degrades gracefully (no crash)."""
    from services.base.task_service import PostProcessFormat

    result = PostProcessFormat(
        payload={"config": {"top_k": 3}},
        response_data=[{"target": "a"}],
        source_texts=["namaste"],
    )
    response = await transliteration_service.postprocess_output(result)
    assert response == {"output": [{"source": "namaste", "target": ["a"]}]}
