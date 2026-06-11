"""Unit tests for NERTaskService — BPE alignment helpers and postprocess pipeline."""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── _build_word_positions ─────────────────────────────────────────────────────

def test_build_word_positions_returns_correct_char_offsets(ner_service):
    positions = ner_service._build_word_positions("John runs fast")
    assert len(positions) == 3
    assert positions[0] == {"word": "John", "start": 0, "end": 4}
    assert positions[1] == {"word": "runs", "start": 5, "end": 9}
    assert positions[2] == {"word": "fast", "start": 10, "end": 14}


def test_build_word_positions_returns_empty_for_empty_string(ner_service):
    assert ner_service._build_word_positions("") == []


# ── _merge_bpe ────────────────────────────────────────────────────────────────

def test_merge_bpe_returns_single_plain_token(ner_service):
    preds = [{"entity": "Hello"}]
    assert ner_service._merge_bpe(preds, 0, 1) == "Hello"


def test_merge_bpe_strips_hash_prefix_and_concatenates(ner_service):
    preds = [{"entity": "New"}, {"entity": "##York"}]
    result = ner_service._merge_bpe(preds, 0, 2)
    assert result == "NewYork"


# ── _group_bpe_tokens ─────────────────────────────────────────────────────────

def test_group_bpe_tokens_returns_empty_for_empty_input(ner_service):
    assert ner_service._group_bpe_tokens([]) == []


def test_group_bpe_tokens_groups_continuation_tokens(ner_service):
    preds = [
        {"entity": "New", "tag": "LOC"},
        {"entity": "##York", "tag": "LOC"},
    ]
    groups = ner_service._group_bpe_tokens(preds)
    assert len(groups) == 1
    assert groups[0]["entity"] == "NewYork"
    assert groups[0]["tag"] == "LOC"


def test_group_bpe_tokens_separates_independent_tokens(ner_service):
    preds = [
        {"entity": "John", "tag": "PERSON"},
        {"entity": "lives", "tag": "O"},
    ]
    groups = ner_service._group_bpe_tokens(preds)
    assert len(groups) == 2
    assert groups[0]["entity"] == "John"
    assert groups[1]["entity"] == "lives"


# ── _align_tags_to_words ──────────────────────────────────────────────────────

def test_align_tags_maps_entity_to_overlapping_word(ner_service):
    word_positions = [
        {"word": "John", "start": 0, "end": 4},
        {"word": "runs", "start": 5, "end": 9},
    ]
    groups = [{"tag": "PERSON", "entity": "John"}]
    aligned = ner_service._align_tags_to_words(word_positions, groups, "John runs")
    assert 0 in aligned
    assert aligned[0]["tag"] == "PERSON"
    assert 1 not in aligned


def test_align_tags_is_case_insensitive(ner_service):
    word_positions = [{"word": "JOHN", "start": 0, "end": 4}]
    groups = [{"tag": "PERSON", "entity": "john"}]
    aligned = ner_service._align_tags_to_words(word_positions, groups, "JOHN")
    assert aligned[0]["tag"] == "PERSON"


# ── _build_ner_token_predictions ─────────────────────────────────────────────

def test_build_ner_token_predictions_assigns_O_for_unaligned_words(ner_service):
    word_positions = [
        {"word": "John", "start": 0, "end": 4},
        {"word": "runs", "start": 5, "end": 9},
    ]
    aligned = {0: {"tag": "PERSON"}}
    result = ner_service._build_ner_token_predictions(word_positions, aligned)
    assert result[0]["tag"] == "PERSON"
    assert result[0]["tokenStartIndex"] == 0
    assert result[0]["tokenEndIndex"] == 4
    assert result[1]["tag"] == "O"


# ── postprocess_output ────────────────────────────────────────────────────────

async def test_postprocess_output_produces_per_token_predictions(ner_service):
    from services.base.task_service import PostProcessFormat
    result = PostProcessFormat(
        payload={"config": {}, "input": [{"source": "John runs"}]},
        response_data=[{
            "target": {
                "output": [{
                    "source": "John runs",
                    "nerPrediction": [
                        {"entity": "John", "tag": "PERSON"},
                        {"entity": "runs", "tag": "O"},
                    ],
                }]
            }
        }],
        source_texts=["John runs"],
    )
    output = await ner_service.postprocess_output(result)
    assert output["taskType"] == "ner"
    preds = output["output"][0]["nerPrediction"]
    assert preds[0]["token"] == "John"
    assert preds[0]["tag"] == "PERSON"
    assert preds[0]["tokenIndex"] == 0
    assert preds[1]["token"] == "runs"
    assert preds[1]["tag"] == "O"


async def test_postprocess_raises_for_non_json_string_target(ner_service):
    from services.base.task_service import PostProcessFormat
    result = PostProcessFormat(
        payload={"config": {}, "input": []},
        response_data=[{"target": "invalid non-json string from model"}],
        source_texts=[],
    )
    with pytest.raises(ValueError, match="non-JSON output"):
        await ner_service.postprocess_output(result)
