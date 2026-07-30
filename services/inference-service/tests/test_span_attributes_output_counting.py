"""Unit tests: count_output_tokens for OCR (AI4IDS-2532 follow-up).

OCR's unit_type is "images" (inference_types.yaml), but OCR never outputs
images — its output is extracted text. count_output_tokens used to route
"images" to a dead, size-based heuristic (_count_output_image_tokens) that
checked for image_content/image fields OCR's response never has (its real
adapter_config maps_to is "text" — see test_config_mapper_shaping.py's
OCR contract fixture), so it always returned 0. It now routes to the same
character-counting used for every other text-output service.
"""
import sys

sys.path.insert(0, ".")

from trace.span_attributes import count_output_tokens


def test_ocr_output_counts_extracted_text_characters():
    response_data = [{"text": "hello world"}]
    assert count_output_tokens(response_data, "images") == len("hello world")


def test_ocr_output_zero_when_no_text():
    response_data = [{"text": ""}]
    assert count_output_tokens(response_data, "images") == 0


def test_ocr_output_sums_across_batch_items():
    response_data = [{"text": "abc"}, {"text": "de"}]
    assert count_output_tokens(response_data, "images") == 5
