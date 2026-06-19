"""OCR response-size load testing framework.

Simulates inference latency for the OCR service using pre-defined
responses — no model is invoked.  Three response sizes are tested
(SMALL, MEDIUM, LARGE) driven by input payload length.

The endpoint accepts either a base64-encoded image (imageContent) or an
image URL (imageUri).  For this test framework, payload size is the length
of the base64 image string, which correlates with image complexity and text
density.  Sample payloads below are minimal base64 strings that hit each
size bucket; in real testing, swap them for actual base64 image content.

Key structural differences from other services:
  - output[0]["source"] is a JSON *string* — not a dict.  Callers must
    json.loads() it to access text_lines, full_text, and image_bbox.
  - output[0]["target"] is always an empty string ""
  - "config" is fully populated: serviceId, language, textDetection
  - "smr_response" is present and null (unlike diarization services)
  - No "taskType" at the top level

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/ocr_response_test.py -v

Or run the module directly for a live console report:

    python response_test/ocr_response_test.py
"""

import sys
import os
import base64
import json
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.ocr_responses import (
    SMALL_OCR_RESPONSE,
    MEDIUM_OCR_RESPONSE,
    LARGE_OCR_RESPONSE,
)


# ---------------------------------------------------------------------------
# OCR tester
# ---------------------------------------------------------------------------

class OCRResponseTest(BaseResponseTest):
    """Load-test harness for OCR inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_OCR_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_OCR_RESPONSE,
        ResponseSize.LARGE:  LARGE_OCR_RESPONSE,
    }

    def get_response(self, size: ResponseSize) -> dict:
        return self._responses[size]


# ---------------------------------------------------------------------------
# Sample payloads (base64-encoded image content)
# ---------------------------------------------------------------------------

# Minimal base64 strings that land in each size bucket.
# Replace with real base64 image content for integration-style runs.
SMALL_PAYLOAD  = base64.b64encode(b"\xff\xd8" + b"\x00" * 28).decode()   #  ~80 chars → SMALL
MEDIUM_PAYLOAD = base64.b64encode(b"\xff\xd8" + b"\x00" * 148).decode()  # ~400 chars → MEDIUM
LARGE_PAYLOAD  = base64.b64encode(b"\xff\xd8" + b"\x00" * 798).decode()  # ~2136 chars → LARGE


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ocr_tester() -> OCRResponseTest:
    return OCRResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, ocr_tester):
        assert ocr_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, ocr_tester):
        assert ocr_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, ocr_tester):
        assert ocr_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, ocr_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "A" * ocr_tester.small_threshold
        assert ocr_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, ocr_tester):
        payload_at_boundary = "A" * ocr_tester.medium_threshold
        assert ocr_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, ocr_tester):
        assert ocr_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestOCRResponses:
    def _parse_source(self, response: dict) -> dict:
        """source is a JSON string — parse it once per assertion helper."""
        return json.loads(response["output"][0]["source"])

    def _assert_valid_ocr_response(self, response: dict) -> None:
        assert "output" in response
        assert "config" in response
        assert "smr_response" in response
        assert response["smr_response"] is None
        # No taskType at the top level for OCR
        assert "taskType" not in response
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        output_item = response["output"][0]
        assert "source" in output_item
        assert "target" in output_item
        # source is a JSON string, not a dict
        assert isinstance(output_item["source"], str)
        assert output_item["target"] == ""
        config = response["config"]
        assert config is not None
        assert "serviceId" in config
        assert "language" in config
        assert "textDetection" in config
        assert "sourceLanguage" in config["language"]
        assert "sourceScriptCode" in config["language"]
        # Validate the stringified source payload
        source = self._parse_source(response)
        assert "success" in source
        assert source["success"] is True
        assert "text_lines" in source
        assert "full_text" in source
        assert "image_bbox" in source
        assert isinstance(source["text_lines"], list)
        assert len(source["text_lines"]) > 0
        assert isinstance(source["full_text"], str)
        assert len(source["image_bbox"]) == 4
        for line in source["text_lines"]:
            assert "text" in line
            assert "confidence" in line
            assert "bbox" in line
            assert "polygon" in line
            assert isinstance(line["text"], str)
            assert isinstance(line["confidence"], float)
            assert 0.0 <= line["confidence"] <= 1.0
            assert len(line["bbox"]) == 4
            assert all(isinstance(v, float) for v in line["bbox"])
            assert len(line["polygon"]) == 4
            for point in line["polygon"]:
                assert len(point) == 2
                assert all(isinstance(v, float) for v in point)

    def test_small_response_has_valid_structure(self, ocr_tester):
        response = ocr_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_ocr_response(response)

    def test_medium_response_has_valid_structure(self, ocr_tester):
        response = ocr_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_ocr_response(response)

    def test_large_response_has_valid_structure(self, ocr_tester):
        response = ocr_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_ocr_response(response)

    def test_source_is_json_string_not_dict(self, ocr_tester):
        for size in ResponseSize:
            output_item = ocr_tester.get_response(size)["output"][0]
            assert isinstance(output_item["source"], str)
            # Must be valid JSON
            parsed = json.loads(output_item["source"])
            assert isinstance(parsed, dict)

    def test_target_is_empty_string(self, ocr_tester):
        for size in ResponseSize:
            output_item = ocr_tester.get_response(size)["output"][0]
            assert output_item["target"] == ""

    def test_full_text_matches_text_lines(self, ocr_tester):
        for size in ResponseSize:
            source = json.loads(ocr_tester.get_response(size)["output"][0]["source"])
            expected = "\n".join(line["text"] for line in source["text_lines"])
            assert source["full_text"] == expected

    def test_text_line_count_increases_with_payload_size(self, ocr_tester):
        small_count = len(json.loads(
            ocr_tester.get_response(ResponseSize.SMALL)["output"][0]["source"]
        )["text_lines"])
        large_count = len(json.loads(
            ocr_tester.get_response(ResponseSize.LARGE)["output"][0]["source"]
        )["text_lines"])
        assert large_count > small_count

    def test_smr_response_is_null(self, ocr_tester):
        for size in ResponseSize:
            assert ocr_tester.get_response(size)["smr_response"] is None

    def test_no_tasktype_at_top_level(self, ocr_tester):
        for size in ResponseSize:
            assert "taskType" not in ocr_tester.get_response(size)

    def test_config_text_detection_is_true(self, ocr_tester):
        for size in ResponseSize:
            assert ocr_tester.get_response(size)["config"]["textDetection"] is True


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, ocr_tester):
        metrics, response = ocr_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, ocr_tester):
        metrics, response = ocr_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, ocr_tester):
        metrics, response = ocr_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, ocr_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = ocr_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, ocr_tester):
        metrics, _ = ocr_tester.run(SMALL_PAYLOAD)
        report = str(metrics)
        assert "Payload Size" in report
        assert "Response Type" in report
        assert "Response Time" in report


# ---------------------------------------------------------------------------
# Load simulation
# ---------------------------------------------------------------------------

class TestLoadSimulation:
    """Run a batch of N requests and verify all metrics are captured."""

    BATCH_SIZE = 20

    def _make_batch(self) -> list[str]:
        payloads = [SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD]
        return [payloads[i % 3] for i in range(self.BATCH_SIZE)]

    def test_batch_produces_metrics_for_every_request(self, ocr_tester):
        results = [ocr_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, ocr_tester):
        results = [ocr_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, ocr_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [ocr_tester.run(p) for p in batch]

        print("\n" + "=" * 50)
        print("OCR Load Simulation — Batch Summary")
        print("=" * 50)
        for metrics, _ in results:
            print(metrics)
            print("-" * 30)

        total_ms = sum(m.duration_ms for m, _ in results)
        avg_ms = total_ms / len(results)
        print(f"\nRequests : {len(results)}")
        print(f"Total    : {total_ms:.3f} ms")
        print(f"Average  : {avg_ms:.3f} ms")
        print("=" * 50)

        captured = capsys.readouterr()
        assert "OCR Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python ocr_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = OCRResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 50)
    print("OCR Response-Size Load Testing — Demo Run")
    print("=" * 50)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        source = json.loads(response["output"][0]["source"])
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Text lines        : {len(source['text_lines'])}")
        preview = source["full_text"][:60].replace("\n", " / ")
        print(f"Full text preview : {preview}...")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
