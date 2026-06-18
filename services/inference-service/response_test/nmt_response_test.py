"""NMT response-size load testing framework.

Simulates inference latency for the NMT service using pre-defined
responses — no model is invoked.  Three response sizes are tested (SMALL,
MEDIUM, LARGE) driven by input payload length.

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/nmt_response_test.py -v

Or run the module directly for a live console report:

    python response_test/nmt_response_test.py
"""

import sys
import os
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.nmt_responses import (
    SMALL_NMT_RESPONSE,
    MEDIUM_NMT_RESPONSE,
    LARGE_NMT_RESPONSE,
)


# ---------------------------------------------------------------------------
# NMT-specific tester
# ---------------------------------------------------------------------------

class NMTResponseTest(BaseResponseTest):
    """Load-test harness for NMT inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_NMT_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_NMT_RESPONSE,
        ResponseSize.LARGE:  LARGE_NMT_RESPONSE,
    }

    def get_response(self, size: ResponseSize) -> dict:
        return self._responses[size]


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

SMALL_PAYLOAD = "Hello how are you"                      # 17 chars  → SMALL
MEDIUM_PAYLOAD = (
    "The meeting has been scheduled for Monday morning at ten o'clock. "
    "Please make sure all the required documents are ready before the session. "
    "Kindly confirm your attendance by replying to this message. "
    "The agenda will be shared with all participants by end of day Friday."
)                                                        # ~268 chars → MEDIUM
LARGE_PAYLOAD = (
    "Artificial intelligence is transforming the way we interact with technology in our daily lives. "
    "From healthcare to education, AI-powered systems are helping professionals make faster and more accurate decisions. "
    "In the field of natural language processing, models can now translate text between hundreds of languages with remarkable accuracy. "
    "This has opened up new possibilities for cross-cultural communication and global collaboration. "
    "Governments and organizations around the world are investing heavily in AI research and development. "
    "However, it is equally important to address the ethical challenges that come with these advancements, "
    "including data privacy, algorithmic bias, and the impact on employment. "
    "A balanced approach that promotes innovation while safeguarding human rights will be essential "
    "for ensuring that AI benefits everyone equally. "
    "Researchers are also exploring how AI can be made more transparent and explainable, "
    "so that users can better understand and trust the decisions made by automated systems. "
    "International cooperation will play a key role in setting standards and governance frameworks."
)                                                        # ~1090 chars → LARGE


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def nmt_tester() -> NMTResponseTest:
    return NMTResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, nmt_tester):
        assert nmt_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, nmt_tester):
        assert nmt_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, nmt_tester):
        assert nmt_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, nmt_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "x" * nmt_tester.small_threshold
        assert nmt_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, nmt_tester):
        payload_at_boundary = "x" * nmt_tester.medium_threshold
        assert nmt_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, nmt_tester):
        assert nmt_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestNMTResponses:
    def _assert_valid_nmt_response(self, response: dict) -> None:
        assert "output" in response
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        assert "smr_response" in response
        for item in response["output"]:
            assert "source" in item
            assert "target" in item
            assert isinstance(item["source"], str)
            assert isinstance(item["target"], str)
            assert len(item["target"]) > 0

    def test_small_response_has_valid_structure(self, nmt_tester):
        response = nmt_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_nmt_response(response)

    def test_medium_response_has_valid_structure(self, nmt_tester):
        response = nmt_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_nmt_response(response)

    def test_large_response_has_valid_structure(self, nmt_tester):
        response = nmt_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_nmt_response(response)

    def test_large_response_target_is_longer_than_small(self, nmt_tester):
        small_target = nmt_tester.get_response(ResponseSize.SMALL)["output"][0]["target"]
        large_target = nmt_tester.get_response(ResponseSize.LARGE)["output"][0]["target"]
        assert len(large_target) > len(small_target)

    def test_smr_response_is_none(self, nmt_tester):
        for size in ResponseSize:
            response = nmt_tester.get_response(size)
            assert response["smr_response"] is None


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, nmt_tester):
        metrics, response = nmt_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, nmt_tester):
        metrics, response = nmt_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, nmt_tester):
        metrics, response = nmt_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, nmt_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = nmt_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, nmt_tester):
        metrics, _ = nmt_tester.run(SMALL_PAYLOAD)
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

    def test_batch_produces_metrics_for_every_request(self, nmt_tester):
        results = [nmt_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, nmt_tester):
        results = [nmt_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, nmt_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [nmt_tester.run(p) for p in batch]

        print("\n" + "=" * 50)
        print("NMT Load Simulation — Batch Summary")
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
        assert "NMT Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python nmt_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = NMTResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 55)
    print("NMT Response-Size Load Testing — Demo Run")
    print("=" * 55)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        target = response["output"][0]["target"]
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Translated target length : {len(target)} chars")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
