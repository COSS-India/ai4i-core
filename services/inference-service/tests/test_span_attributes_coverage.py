"""Extended coverage for trace.span_attributes edge cases."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from trace import span_attributes as sa


class TestGetInputTypeEdgeCases:
    def test_image_payload(self):
        assert sa.get_input_type({"image": [{"imageContent": "abc"}]}) == "image"

    def test_non_dict_payload(self):
        assert sa.get_input_type(None) == "unknown"
        assert sa.get_input_type([]) == "unknown"

    def test_exception_returns_unknown(self):
        class BadPayload(dict):
            def get(self, key, default=None):
                raise RuntimeError("boom")

        assert sa.get_input_type(BadPayload({"input": [{"source": "x"}]})) == "unknown"


class TestGetOutputTypeEdgeCases:
    def test_transcription_and_translation_keys(self):
        assert sa.get_output_type([{"transcription": "hello"}]) == "text"
        assert sa.get_output_type([{"translation": "namaste"}]) == "text"

    def test_waveform_and_encoding_keys(self):
        assert sa.get_output_type([{"waveform": [1, 2]}]) == "audio"
        assert sa.get_output_type([{"encoding": "png"}]) == "image"

    def test_non_list_or_empty(self):
        assert sa.get_output_type(None) == "unknown"
        assert sa.get_output_type([]) == "unknown"

    def test_non_dict_first_item(self):
        assert sa.get_output_type(["not-a-dict"]) == "unknown"

    def test_unknown_keys(self):
        assert sa.get_output_type([{"unexpected": "value"}]) == "unknown"

    def test_exception_returns_unknown(self):
        with patch("trace.span_attributes.logger"):
            assert sa.get_output_type(object()) == "unknown"


class TestCountInputTokensEdgeCases:
    def test_text_with_object_items(self):
        item = SimpleNamespace(source="one two three")
        assert sa.count_input_tokens([item], "text") == 3

    def test_audio_with_content_heuristic(self):
        items = [{"audio_content": "x" * 250}]
        assert sa.count_input_tokens(items, "audio") >= 2

    def test_image_tokens(self):
        items = [{"image_content": "x" * 2500}]
        assert sa.count_input_tokens(items, "image") >= 2

    def test_empty_items(self):
        assert sa.count_input_tokens([], "text") == 0

    def test_unknown_input_type(self):
        assert sa.count_input_tokens([{"source": "a"}], "unknown") == 0

    def test_exception_returns_zero(self):
        with patch("trace.span_attributes._count_text_tokens", side_effect=RuntimeError("x")):
            assert sa.count_input_tokens([{"source": "a"}], "text") == 0


class TestCountOutputTokensEdgeCases:
    def test_text_output_and_bytes(self):
        data = [{"target": b"hello world"}]
        assert sa.count_output_tokens(data, "text") == 2

    def test_text_output_field_variants(self):
        assert sa.count_output_tokens([{"output": "one"}], "text") == 1
        assert sa.count_output_tokens([{"text": "two words"}], "text") == 2

    def test_audio_output(self):
        data = [{"audio": "x" * 300}]
        assert sa.count_output_tokens(data, "audio") >= 3

    def test_image_output(self):
        data = [{"image": "x" * 3000}]
        assert sa.count_output_tokens(data, "image") >= 3

    def test_empty_or_unknown_type(self):
        assert sa.count_output_tokens([], "text") == 0
        assert sa.count_output_tokens([{"target": "x"}], "unknown") == 0

    def test_exception_returns_zero(self):
        with patch("trace.span_attributes._count_output_text_tokens", side_effect=RuntimeError("x")):
            assert sa.count_output_tokens([{"target": "a"}], "text") == 0
