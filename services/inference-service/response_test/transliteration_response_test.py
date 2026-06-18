"""Transliteration response-size load testing framework.

Simulates inference latency for the Transliteration service using pre-defined
responses — no model is invoked.  Three response sizes are tested (SMALL,
MEDIUM, LARGE) driven by input payload length.

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/transliteration_response_test.py -v

Or run the module directly for a live console report:

    python response_test/transliteration_response_test.py
"""

import sys
import os
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.transliteration_responses import (
    SMALL_TRANSLITERATION_RESPONSE,
    MEDIUM_TRANSLITERATION_RESPONSE,
    LARGE_TRANSLITERATION_RESPONSE,
)


# ---------------------------------------------------------------------------
# Transliteration-specific tester
# ---------------------------------------------------------------------------

class TransliterationResponseTest(BaseResponseTest):
    """Load-test harness for Transliteration inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_TRANSLITERATION_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_TRANSLITERATION_RESPONSE,
        ResponseSize.LARGE:  LARGE_TRANSLITERATION_RESPONSE,
    }

    def get_response(self, size: ResponseSize) -> dict:
        return self._responses[size]


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

SMALL_PAYLOAD = "Hello Good Morning"                      # 18 chars  → SMALL
MEDIUM_PAYLOAD = (
    "My name is Ravi Kumar and I am from Mumbai Maharashtra. "
    "I work at a software company in Bangalore and I enjoy my work very much. "
    "Today the weather is very nice so I am going to the market with my family "
    "to buy some vegetables and fruits for the week."
)                                                         # ~250 chars → MEDIUM
LARGE_PAYLOAD = (
    "India is a country with a rich cultural heritage and a diverse population. "
    "People from different states speak different languages and follow different traditions. "
    "The festivals of India are celebrated with great enthusiasm and joy across the country. "
    "Diwali, Holi, Eid, Christmas, and Pongal are some of the most popular festivals. "
    "The cuisine of India varies from region to region and is known for its rich flavors and spices. "
    "Indian classical music and dance forms like Bharatanatyam, Kathak, and Odissi have a long history. "
    "The film industry in India, commonly known as Bollywood, produces hundreds of movies every year. "
    "India has also made significant contributions to science, mathematics, and technology. "
    "The space programme of India has achieved remarkable milestones in recent years. "
    "Young people in India are increasingly interested in entrepreneurship and innovation, "
    "and many startups from India have become globally recognized companies. "
    "The education system in India continues to evolve to meet the demands of a modern economy."
)                                                         # ~1040 chars → LARGE


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def transliteration_tester() -> TransliterationResponseTest:
    return TransliterationResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, transliteration_tester):
        assert transliteration_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, transliteration_tester):
        assert transliteration_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, transliteration_tester):
        assert transliteration_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, transliteration_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "x" * transliteration_tester.small_threshold
        assert transliteration_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, transliteration_tester):
        payload_at_boundary = "x" * transliteration_tester.medium_threshold
        assert transliteration_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, transliteration_tester):
        assert transliteration_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestTransliterationResponses:
    def _assert_valid_transliteration_response(self, response: dict) -> None:
        assert "output" in response
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        # no smr_response, no config, no taskType in transliteration responses
        assert "smr_response" not in response
        assert "config" not in response
        assert "taskType" not in response
        for item in response["output"]:
            assert "source" in item
            assert "target" in item
            assert isinstance(item["source"], str)
            assert isinstance(item["target"], str)
            assert len(item["target"]) > 0

    def test_small_response_has_valid_structure(self, transliteration_tester):
        response = transliteration_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_transliteration_response(response)

    def test_medium_response_has_valid_structure(self, transliteration_tester):
        response = transliteration_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_transliteration_response(response)

    def test_large_response_has_valid_structure(self, transliteration_tester):
        response = transliteration_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_transliteration_response(response)

    def test_large_response_target_is_longer_than_small(self, transliteration_tester):
        small_target = transliteration_tester.get_response(ResponseSize.SMALL)["output"][0]["target"]
        large_target = transliteration_tester.get_response(ResponseSize.LARGE)["output"][0]["target"]
        assert len(large_target) > len(small_target)

    def test_small_response_source_matches_payload(self, transliteration_tester):
        response = transliteration_tester.get_response(ResponseSize.SMALL)
        assert response["output"][0]["source"] == SMALL_PAYLOAD


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, transliteration_tester):
        metrics, response = transliteration_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, transliteration_tester):
        metrics, response = transliteration_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, transliteration_tester):
        metrics, response = transliteration_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, transliteration_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = transliteration_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, transliteration_tester):
        metrics, _ = transliteration_tester.run(SMALL_PAYLOAD)
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

    def test_batch_produces_metrics_for_every_request(self, transliteration_tester):
        results = [transliteration_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, transliteration_tester):
        results = [transliteration_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, transliteration_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [transliteration_tester.run(p) for p in batch]

        print("\n" + "=" * 50)
        print("Transliteration Load Simulation — Batch Summary")
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
        assert "Transliteration Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python transliteration_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = TransliterationResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 55)
    print("Transliteration Response-Size Load Testing — Demo Run")
    print("=" * 55)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        target = response["output"][0]["target"]
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Transliterated target length : {len(target)} chars")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
