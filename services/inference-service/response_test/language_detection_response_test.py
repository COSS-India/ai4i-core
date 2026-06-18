"""Language Detection response-size load testing framework.

Simulates inference latency for the Language Detection service using pre-defined
responses — no model is invoked.  Three response sizes are tested (SMALL,
MEDIUM, LARGE) driven by input payload length.

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/language_detection_response_test.py -v

Or run the module directly for a live console report:

    python response_test/language_detection_response_test.py
"""

import sys
import os
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.language_detection_responses import (
    SMALL_LANGUAGE_DETECTION_RESPONSE,
    MEDIUM_LANGUAGE_DETECTION_RESPONSE,
    LARGE_LANGUAGE_DETECTION_RESPONSE,
)


# ---------------------------------------------------------------------------
# Language-Detection-specific tester
# ---------------------------------------------------------------------------

class LanguageDetectionResponseTest(BaseResponseTest):
    """Load-test harness for Language Detection inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_LANGUAGE_DETECTION_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_LANGUAGE_DETECTION_RESPONSE,
        ResponseSize.LARGE:  LARGE_LANGUAGE_DETECTION_RESPONSE,
    }

    def get_response(self, size: ResponseSize) -> dict:
        return self._responses[size]


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

SMALL_PAYLOAD = "hello how are you"                       # 17 chars  → SMALL
MEDIUM_PAYLOAD = (
    "The quick brown fox jumps over the lazy dog. "
    "This sentence contains every letter of the English alphabet at least once. "
    "It is commonly used for testing fonts and keyboards. "
    "The weather today is sunny with clear skies and a gentle breeze."
)                                                         # ~237 chars → MEDIUM
LARGE_PAYLOAD = (
    "Language detection is the process of identifying the natural language of a given text. "
    "It is a fundamental step in many natural language processing pipelines. "
    "Modern language detection models can identify hundreds of languages with high accuracy. "
    "The challenge increases when the input text is short or contains mixed languages. "
    "Indic languages present unique challenges because many share similar scripts. "
    "For example, Hindi, Marathi, and Sanskrit all use the Devanagari script. "
    "Bengali and Assamese share a very similar script as well. "
    "Models like IndicLID are specifically trained to distinguish between these closely related languages. "
    "They use both the character n-gram features and the script information together. "
    "In a multilingual country like India, accurate language detection is critical "
    "for routing text to the correct downstream service such as translation or transliteration. "
    "Low-resource languages benefit the most from dedicated detection models "
    "because general-purpose models often confuse them with higher-resource cousins."
)                                                         # ~1041 chars → LARGE


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ld_tester() -> LanguageDetectionResponseTest:
    return LanguageDetectionResponseTest()


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
        payload_at_boundary = "x" * ld_tester.small_threshold
        assert ld_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, ld_tester):
        payload_at_boundary = "x" * ld_tester.medium_threshold
        assert ld_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, ld_tester):
        assert ld_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestLanguageDetectionResponses:
    def _assert_valid_ld_response(self, response: dict) -> None:
        assert "output" in response
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        assert "config" in response
        for item in response["output"]:
            assert "source" in item
            assert "langPrediction" in item
            assert isinstance(item["source"], str)
            assert isinstance(item["langPrediction"], list)
            assert len(item["langPrediction"]) > 0
            for pred in item["langPrediction"]:
                assert "langCode" in pred
                assert "confidence" in pred
                assert "model" in pred
                assert "input" in pred
                assert isinstance(pred["langCode"], str)
                assert isinstance(pred["confidence"], float)
                assert 0.0 <= pred["confidence"] <= 1.0
                assert isinstance(pred["model"], str)

    def test_small_response_has_valid_structure(self, ld_tester):
        response = ld_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_ld_response(response)

    def test_medium_response_has_valid_structure(self, ld_tester):
        response = ld_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_ld_response(response)

    def test_large_response_has_valid_structure(self, ld_tester):
        response = ld_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_ld_response(response)

    def test_config_is_present_and_none(self, ld_tester):
        for size in ResponseSize:
            response = ld_tester.get_response(size)
            assert "config" in response
            assert response["config"] is None

    def test_small_response_source_matches_payload(self, ld_tester):
        response = ld_tester.get_response(ResponseSize.SMALL)
        assert response["output"][0]["source"] == SMALL_PAYLOAD

    def test_large_response_confidence_higher_than_small(self, ld_tester):
        small_conf = ld_tester.get_response(ResponseSize.SMALL)["output"][0]["langPrediction"][0]["confidence"]
        large_conf = ld_tester.get_response(ResponseSize.LARGE)["output"][0]["langPrediction"][0]["confidence"]
        # More text → higher confidence is expected in realistic responses
        assert large_conf > small_conf


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

        print("\n" + "=" * 50)
        print("Language Detection Load Simulation — Batch Summary")
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
        assert "Language Detection Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python language_detection_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = LanguageDetectionResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 55)
    print("Language Detection Response-Size Load Testing — Demo Run")
    print("=" * 55)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        pred = response["output"][0]["langPrediction"][0]
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Detected language : {pred['langCode']}  (confidence: {pred['confidence']:.4f})")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
