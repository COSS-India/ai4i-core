"""ASR response-size load testing framework.

Simulates inference latency for the ASR service using pre-defined
responses — no model is invoked.  Three response sizes are tested (SMALL,
MEDIUM, LARGE) driven by input payload length.

The ASR endpoint receives base64-encoded audio as input.  Payload size is
therefore the length of the base64 string, which correlates with audio
duration.  Sample payloads below are minimal base64 strings that hit each
size bucket; in real testing, swap them for actual base64 audio content.

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/asr_response_test.py -v

Or run the module directly for a live console report:

    python response_test/asr_response_test.py
"""

import sys
import os
import base64
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.asr_responses import (
    SMALL_ASR_RESPONSE,
    MEDIUM_ASR_RESPONSE,
    LARGE_ASR_RESPONSE,
)


# ---------------------------------------------------------------------------
# ASR-specific tester
# ---------------------------------------------------------------------------

class ASRResponseTest(BaseResponseTest):
    """Load-test harness for ASR inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_ASR_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_ASR_RESPONSE,
        ResponseSize.LARGE:  LARGE_ASR_RESPONSE,
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
def asr_tester() -> ASRResponseTest:
    return ASRResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, asr_tester):
        assert asr_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, asr_tester):
        assert asr_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, asr_tester):
        assert asr_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, asr_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "A" * asr_tester.small_threshold
        assert asr_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, asr_tester):
        payload_at_boundary = "A" * asr_tester.medium_threshold
        assert asr_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, asr_tester):
        assert asr_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestASRResponses:
    def _assert_valid_asr_response(self, response: dict) -> None:
        assert "output" in response
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        # Both envelope fields are present (no response_model_exclude on ASR route)
        assert "config" in response
        assert "smr_response" in response
        assert response["config"] is None
        assert response["smr_response"] is None
        for item in response["output"]:
            assert "source" in item
            assert "nBestTokens" in item
            assert isinstance(item["source"], str)
            assert len(item["source"]) > 0
            assert item["nBestTokens"] is None

    def test_small_response_has_valid_structure(self, asr_tester):
        response = asr_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_asr_response(response)

    def test_medium_response_has_valid_structure(self, asr_tester):
        response = asr_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_asr_response(response)

    def test_large_response_has_valid_structure(self, asr_tester):
        response = asr_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_asr_response(response)

    def test_large_transcript_is_longer_than_small(self, asr_tester):
        small_src = asr_tester.get_response(ResponseSize.SMALL)["output"][0]["source"]
        large_src = asr_tester.get_response(ResponseSize.LARGE)["output"][0]["source"]
        assert len(large_src) > len(small_src)

    def test_nbest_tokens_is_none_for_all_sizes(self, asr_tester):
        for size in ResponseSize:
            response = asr_tester.get_response(size)
            assert response["output"][0]["nBestTokens"] is None


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, asr_tester):
        metrics, response = asr_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, asr_tester):
        metrics, response = asr_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, asr_tester):
        metrics, response = asr_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, asr_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = asr_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, asr_tester):
        metrics, _ = asr_tester.run(SMALL_PAYLOAD)
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

    def test_batch_produces_metrics_for_every_request(self, asr_tester):
        results = [asr_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, asr_tester):
        results = [asr_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, asr_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [asr_tester.run(p) for p in batch]

        print("\n" + "=" * 50)
        print("ASR Load Simulation — Batch Summary")
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
        assert "ASR Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python asr_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = ASRResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 55)
    print("ASR Response-Size Load Testing — Demo Run")
    print("=" * 55)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        transcript = response["output"][0]["source"]
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Transcript length : {len(transcript)} chars")
        print(f"Transcript        : {transcript[:60]}{'...' if len(transcript) > 60 else ''}")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
