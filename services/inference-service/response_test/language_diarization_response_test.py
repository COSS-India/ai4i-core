"""Language Diarization response-size load testing framework.

Simulates inference latency for the Language Diarization service using
pre-defined responses — no model is invoked.  Three response sizes are tested
(SMALL, MEDIUM, LARGE) driven by input payload length.

The endpoint receives base64-encoded audio as input.  Payload size is therefore
the length of the base64 string, which correlates with audio duration.  Sample
payloads below are minimal base64 strings that hit each size bucket; in real
testing, swap them for actual base64 audio content.

Key structural differences from other services:
  - "taskType" is present: "language-diarization"
  - Output item contains "total_segments", "segments", and "target_language"
    (not a flat list of predictions like other services)
  - Each segment has "start_time", "end_time", "duration", "language",
    "confidence"
  - "config" is populated with "serviceId" (not null)
  - "smr_response" is absent entirely (not present in the response)

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/language_diarization_response_test.py -v

Or run the module directly for a live console report:

    python response_test/language_diarization_response_test.py
"""

import sys
import os
import base64
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.language_diarization_responses import (
    SMALL_LANGUAGE_DIARIZATION_RESPONSE,
    MEDIUM_LANGUAGE_DIARIZATION_RESPONSE,
    LARGE_LANGUAGE_DIARIZATION_RESPONSE,
)


# ---------------------------------------------------------------------------
# Language Diarization tester
# ---------------------------------------------------------------------------

class LanguageDiarizationResponseTest(BaseResponseTest):
    """Load-test harness for Language Diarization inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_LANGUAGE_DIARIZATION_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_LANGUAGE_DIARIZATION_RESPONSE,
        ResponseSize.LARGE:  LARGE_LANGUAGE_DIARIZATION_RESPONSE,
    }

    def get_response(self, size: ResponseSize) -> dict:
        return self._responses[size]


# ---------------------------------------------------------------------------
# Sample payloads (base64-encoded audio content)
# ---------------------------------------------------------------------------

# Minimal base64 strings that land in each size bucket.
# Replace with real base64 audio for integration-style runs.
SMALL_PAYLOAD  = base64.b64encode(b"\x00\x01" * 30).decode()   #  ~80 chars → SMALL
MEDIUM_PAYLOAD = base64.b64encode(b"\x00\x01" * 150).decode()  # ~400 chars → MEDIUM
LARGE_PAYLOAD  = base64.b64encode(b"\x00\x01" * 800).decode()  # ~2136 chars → LARGE


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ld_tester() -> LanguageDiarizationResponseTest:
    return LanguageDiarizationResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, ld_tester):
        assert ld_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, ld_tester):
        assert ld_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, ld_tester):
        assert ld_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, ld_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "A" * ld_tester.small_threshold
        assert ld_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, ld_tester):
        payload_at_boundary = "A" * ld_tester.medium_threshold
        assert ld_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, ld_tester):
        assert ld_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestLanguageDiarizationResponses:
    def _assert_valid_ld_response(self, response: dict) -> None:
        assert "taskType" in response
        assert response["taskType"] == "language-diarization"
        assert "output" in response
        assert "config" in response
        # smr_response is absent — the route does not include it
        assert "smr_response" not in response
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        config = response["config"]
        assert config is not None
        assert "serviceId" in config
        output_item = response["output"][0]
        assert "total_segments" in output_item
        assert "segments" in output_item
        assert "target_language" in output_item
        assert isinstance(output_item["total_segments"], int)
        assert output_item["total_segments"] == len(output_item["segments"])
        for segment in output_item["segments"]:
            assert "start_time" in segment
            assert "end_time" in segment
            assert "duration" in segment
            assert "language" in segment
            assert "confidence" in segment
            assert isinstance(segment["start_time"], float)
            assert isinstance(segment["end_time"], float)
            assert isinstance(segment["duration"], float)
            assert isinstance(segment["language"], str)
            assert isinstance(segment["confidence"], float)
            assert 0.0 <= segment["confidence"] <= 1.0
            assert segment["end_time"] > segment["start_time"]

    def test_small_response_has_valid_structure(self, ld_tester):
        response = ld_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_ld_response(response)

    def test_medium_response_has_valid_structure(self, ld_tester):
        response = ld_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_ld_response(response)

    def test_large_response_has_valid_structure(self, ld_tester):
        response = ld_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_ld_response(response)

    def test_tasktype_is_language_diarization(self, ld_tester):
        for size in ResponseSize:
            response = ld_tester.get_response(size)
            assert response["taskType"] == "language-diarization"

    def test_total_segments_matches_segment_list_length(self, ld_tester):
        for size in ResponseSize:
            response = ld_tester.get_response(size)
            output_item = response["output"][0]
            assert output_item["total_segments"] == len(output_item["segments"])

    def test_segment_duration_matches_time_range(self, ld_tester):
        for size in ResponseSize:
            response = ld_tester.get_response(size)
            for segment in response["output"][0]["segments"]:
                expected = round(segment["end_time"] - segment["start_time"], 6)
                assert abs(segment["duration"] - expected) < 0.01, (
                    f"duration {segment['duration']} != end-start "
                    f"({segment['end_time']} - {segment['start_time']} = {expected})"
                )

    def test_segment_count_increases_with_payload_size(self, ld_tester):
        small_count = ld_tester.get_response(ResponseSize.SMALL)["output"][0]["total_segments"]
        large_count = ld_tester.get_response(ResponseSize.LARGE)["output"][0]["total_segments"]
        assert large_count > small_count

    def test_target_language_is_all(self, ld_tester):
        for size in ResponseSize:
            response = ld_tester.get_response(size)
            assert response["output"][0]["target_language"] == "all"

    def test_smr_response_absent(self, ld_tester):
        for size in ResponseSize:
            response = ld_tester.get_response(size)
            assert "smr_response" not in response

    def test_config_has_service_id(self, ld_tester):
        for size in ResponseSize:
            response = ld_tester.get_response(size)
            assert "serviceId" in response["config"]
            assert isinstance(response["config"]["serviceId"], str)
            assert len(response["config"]["serviceId"]) > 0


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, ld_tester):
        metrics, response = ld_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, ld_tester):
        metrics, response = ld_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, ld_tester):
        metrics, response = ld_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, ld_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = ld_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, ld_tester):
        metrics, _ = ld_tester.run(SMALL_PAYLOAD)
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

    def test_batch_produces_metrics_for_every_request(self, ld_tester):
        results = [ld_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, ld_tester):
        results = [ld_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, ld_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [ld_tester.run(p) for p in batch]

        print("\n" + "=" * 55)
        print("Language Diarization Load Simulation — Batch Summary")
        print("=" * 55)
        for metrics, _ in results:
            print(metrics)
            print("-" * 30)

        total_ms = sum(m.duration_ms for m, _ in results)
        avg_ms = total_ms / len(results)
        print(f"\nRequests : {len(results)}")
        print(f"Total    : {total_ms:.3f} ms")
        print(f"Average  : {avg_ms:.3f} ms")
        print("=" * 55)

        captured = capsys.readouterr()
        assert "Language Diarization Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python language_diarization_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = LanguageDiarizationResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 60)
    print("Language Diarization Response-Size Load Testing — Demo Run")
    print("=" * 60)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        output_item = response["output"][0]
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Total segments    : {output_item['total_segments']}")
        langs = list({s["language"] for s in output_item["segments"]})
        print(f"Languages seen    : {', '.join(sorted(langs))}")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
