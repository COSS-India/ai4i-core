"""Audio Language Detection response-size load testing framework.

Simulates inference latency for the Audio Language Detection service using
pre-defined responses — no model is invoked.  Three response sizes are tested
(SMALL, MEDIUM, LARGE) driven by input payload length.

The endpoint receives base64-encoded audio as input.  Payload size is therefore
the length of the base64 string, which correlates with audio duration.  Sample
payloads below are minimal base64 strings that hit each size bucket; in real
testing, swap them for actual base64 audio content.

Key structural differences from text language detection and other services:
  - "taskType" is present: "audio-lang-detection"
  - Output items use "language_code" (not "langPrediction")
  - "all_scores" contains "top_scores" — a list of 5 confidence floats
  - "config" is populated with "serviceId" (not null)
  - "smr_response" is absent entirely (not present in the response)

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/audio_lang_detection_response_test.py -v

Or run the module directly for a live console report:

    python response_test/audio_lang_detection_response_test.py
"""

import sys
import os
import base64
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.audio_lang_detection_responses import (
    SMALL_AUDIO_LANG_DETECTION_RESPONSE,
    MEDIUM_AUDIO_LANG_DETECTION_RESPONSE,
    LARGE_AUDIO_LANG_DETECTION_RESPONSE,
)


# ---------------------------------------------------------------------------
# Audio Language Detection tester
# ---------------------------------------------------------------------------

class AudioLangDetectionResponseTest(BaseResponseTest):
    """Load-test harness for Audio Language Detection inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_AUDIO_LANG_DETECTION_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_AUDIO_LANG_DETECTION_RESPONSE,
        ResponseSize.LARGE:  LARGE_AUDIO_LANG_DETECTION_RESPONSE,
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
def ald_tester() -> AudioLangDetectionResponseTest:
    return AudioLangDetectionResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, ald_tester):
        assert ald_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, ald_tester):
        assert ald_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, ald_tester):
        assert ald_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, ald_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "A" * ald_tester.small_threshold
        assert ald_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, ald_tester):
        payload_at_boundary = "A" * ald_tester.medium_threshold
        assert ald_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, ald_tester):
        assert ald_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestAudioLangDetectionResponses:
    def _assert_valid_ald_response(self, response: dict) -> None:
        assert "taskType" in response
        assert response["taskType"] == "audio-lang-detection"
        assert "output" in response
        assert "config" in response
        # smr_response is absent — the route does not include it
        assert "smr_response" not in response
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        config = response["config"]
        assert config is not None
        assert "serviceId" in config
        for item in response["output"]:
            assert "language_code" in item
            assert "confidence" in item
            assert "all_scores" in item
            assert isinstance(item["language_code"], str)
            assert isinstance(item["confidence"], float)
            assert 0.0 <= item["confidence"] <= 1.0
            all_scores = item["all_scores"]
            assert "predicted_language" in all_scores
            assert "confidence" in all_scores
            assert "top_scores" in all_scores
            assert isinstance(all_scores["top_scores"], list)
            assert len(all_scores["top_scores"]) == 5
            assert all(isinstance(s, float) for s in all_scores["top_scores"])

    def test_small_response_has_valid_structure(self, ald_tester):
        response = ald_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_ald_response(response)

    def test_medium_response_has_valid_structure(self, ald_tester):
        response = ald_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_ald_response(response)

    def test_large_response_has_valid_structure(self, ald_tester):
        response = ald_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_ald_response(response)

    def test_tasktype_is_audio_lang_detection(self, ald_tester):
        for size in ResponseSize:
            response = ald_tester.get_response(size)
            assert response["taskType"] == "audio-lang-detection"

    def test_language_code_matches_predicted_language(self, ald_tester):
        for size in ResponseSize:
            response = ald_tester.get_response(size)
            item = response["output"][0]
            assert item["language_code"] == item["all_scores"]["predicted_language"]

    def test_confidence_matches_all_scores_confidence(self, ald_tester):
        for size in ResponseSize:
            response = ald_tester.get_response(size)
            item = response["output"][0]
            assert item["confidence"] == item["all_scores"]["confidence"]

    def test_confidence_increases_with_payload_size(self, ald_tester):
        small_conf = ald_tester.get_response(ResponseSize.SMALL)["output"][0]["confidence"]
        large_conf = ald_tester.get_response(ResponseSize.LARGE)["output"][0]["confidence"]
        assert large_conf > small_conf


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, ald_tester):
        metrics, response = ald_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, ald_tester):
        metrics, response = ald_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, ald_tester):
        metrics, response = ald_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, ald_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = ald_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, ald_tester):
        metrics, _ = ald_tester.run(SMALL_PAYLOAD)
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

    def test_batch_produces_metrics_for_every_request(self, ald_tester):
        results = [ald_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, ald_tester):
        results = [ald_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, ald_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [ald_tester.run(p) for p in batch]

        print("\n" + "=" * 50)
        print("Audio Lang Detection Load Simulation — Batch Summary")
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
        assert "Audio Lang Detection Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python audio_lang_detection_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = AudioLangDetectionResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 57)
    print("Audio Language Detection Response-Size Load Testing — Demo Run")
    print("=" * 57)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        item = response["output"][0]
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Detected language : {item['language_code']}  (confidence: {item['confidence']:.4f})")
        print(f"Top-5 scores      : {[round(s, 4) for s in item['all_scores']['top_scores']]}")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
