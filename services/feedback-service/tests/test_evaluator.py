"""
Unit tests for LLM Judge JSON parsing helpers and PII client language utilities.

No external connections are made — all logic under test is pure Python.
"""

import pytest

from app.services.evaluator import _parse_json_array, _parse_json_object
from app.services.pii_client import _lang_code, _source_lang, _target_lang


# ---------------------------------------------------------------------------
# _parse_json_object
# ---------------------------------------------------------------------------

class TestParseJsonObject:

    def test_clean_json_string(self):
        raw = '{"status": "PASS", "error_type": "None", "severity": "LOW", "reasoning": "ok"}'
        result = _parse_json_object(raw)
        assert result == {
            "status": "PASS",
            "error_type": "None",
            "severity": "LOW",
            "reasoning": "ok",
        }

    def test_prose_before_json(self):
        raw = 'Sure, here is the evaluation: {"status": "FAIL", "error_type": "Meaning Errors", "severity": "HIGH", "reasoning": "wrong meaning"}'
        result = _parse_json_object(raw)
        assert result["status"] == "FAIL"
        assert result["error_type"] == "Meaning Errors"

    def test_prose_after_json(self):
        raw = '{"status": "PASS", "reasoning": "looks good"} Hope this helps!'
        result = _parse_json_object(raw)
        assert result["status"] == "PASS"

    def test_nested_object(self):
        raw = '{"status": "PASS", "data": {"key": "value", "num": 1}}'
        result = _parse_json_object(raw)
        assert result["status"] == "PASS"
        assert result["data"] == {"key": "value", "num": 1}

    def test_empty_string_returns_empty_dict(self):
        assert _parse_json_object("") == {}

    def test_plain_text_returns_empty_dict(self):
        assert _parse_json_object("This is not JSON at all") == {}

    def test_malformed_braces_returns_empty_dict(self):
        assert _parse_json_object("{this: is not valid}") == {}

    def test_object_inside_array_is_extracted(self):
        """The walker finds the first { block even when wrapped in an array."""
        result = _parse_json_object('[{"status": "PASS"}]')
        assert result == {"status": "PASS"}

    def test_markdown_wrapped_json(self):
        """LLMs sometimes wrap output in ```json fences."""
        raw = '```json\n{"status": "PASS", "reasoning": "fine"}\n```'
        result = _parse_json_object(raw)
        assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# _parse_json_array
# ---------------------------------------------------------------------------

class TestParseJsonArray:

    def test_clean_array(self):
        raw = '[{"status": "PASS"}, {"status": "FAIL"}]'
        result = _parse_json_array(raw)
        assert len(result) == 2
        assert result[0]["status"] == "PASS"
        assert result[1]["status"] == "FAIL"

    def test_prose_before_array(self):
        raw = 'Here are the results:\n[{"status": "PASS"}, {"status": "FAIL"}]'
        result = _parse_json_array(raw)
        assert len(result) == 2

    def test_nested_arrays_in_objects(self):
        raw = '[{"status": "PASS", "tags": ["a", "b"]}]'
        result = _parse_json_array(raw)
        assert result[0]["tags"] == ["a", "b"]

    def test_empty_array(self):
        assert _parse_json_array("[]") == []

    def test_empty_string_returns_empty_list(self):
        assert _parse_json_array("") == []

    def test_plain_text_returns_empty_list(self):
        assert _parse_json_array("no array here") == []

    def test_object_input_returns_empty_list(self):
        """A bare object should not be returned as a list."""
        result = _parse_json_array('{"status": "PASS"}')
        assert result == []

    def test_single_element_array(self):
        raw = '[{"status": "FAIL", "error_type": "Grammar Errors", "severity": "LOW", "reason": "minor"}]'
        result = _parse_json_array(raw)
        assert len(result) == 1
        assert result[0]["error_type"] == "Grammar Errors"


# ---------------------------------------------------------------------------
# PII client language helpers
# ---------------------------------------------------------------------------

class TestLangCode:

    def test_plain_code(self):
        assert _lang_code("hi") == "hi"

    def test_strips_script_suffix(self):
        assert _lang_code("hi_Deva") == "hi"

    def test_lowercases(self):
        assert _lang_code("EN") == "en"

    def test_empty_string(self):
        assert _lang_code("") == ""


class TestSourceLang:

    def test_bilingual_pair(self):
        assert _source_lang("hi-en") == "hi"

    def test_single_lang(self):
        assert _source_lang("en") == "en"

    def test_none_returns_empty(self):
        assert _source_lang(None) == ""

    def test_script_suffix_stripped(self):
        assert _source_lang("hi_Deva-en") == "hi"


class TestTargetLang:

    def test_bilingual_pair(self):
        assert _target_lang("hi-en") == "en"

    def test_single_lang_falls_back_to_source(self):
        assert _target_lang("hi") == "hi"

    def test_none_returns_empty(self):
        assert _target_lang(None) == ""
