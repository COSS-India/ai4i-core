"""NER response-size load testing framework.

Simulates inference latency for the NER service using pre-defined
responses — no model is invoked.  Three response sizes are tested (SMALL,
MEDIUM, LARGE) driven by input payload length.

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/ner_response_test.py -v

Or run the module directly for a live console report:

    python response_test/ner_response_test.py
"""

import sys
import os
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.ner_responses import (
    SMALL_NER_RESPONSE,
    MEDIUM_NER_RESPONSE,
    LARGE_NER_RESPONSE,
)


# ---------------------------------------------------------------------------
# NER-specific tester
# ---------------------------------------------------------------------------

class NERResponseTest(BaseResponseTest):
    """Load-test harness for NER inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_NER_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_NER_RESPONSE,
        ResponseSize.LARGE:  LARGE_NER_RESPONSE,
    }

    def get_response(self, size: ResponseSize) -> dict:
        return self._responses[size]


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

SMALL_PAYLOAD = "John visited Paris."                    # 19 chars  → SMALL
MEDIUM_PAYLOAD = (
    "John Smith joined Google in New York last Tuesday. "
    "He will report to Sarah Connor at the Mountain View office. "
    "The project involves teams from Amazon Web Services and IBM Research. "
    "Deliverables are due by the end of Q4."
)                                                        # ~240 chars → MEDIUM
LARGE_PAYLOAD = (
    "Dr. Emily Watson of Harvard University published a landmark study on climate change "
    "with funding from the United Nations Environment Programme and the World Bank. "
    "The research was conducted in collaboration with Professor Arun Mehta at IIT Delhi "
    "and Dr. Lena Fischer at the Max Planck Institute in Berlin, Germany. "
    "The findings were presented at COP28 in Dubai, UAE on December 12, 2023. "
    "Amazon, Microsoft, and Google pledged over $500 million to support the initiative. "
    "The report will be reviewed by the European Parliament and the U.S. Senate "
    "before a final decision is made in January 2024. "
    "Additional stakeholders include the International Monetary Fund, NATO, "
    "the Reserve Bank of India, and the People's Bank of China. "
    "The study references prior work from MIT, Stanford University, and Oxford. "
    "Field data was collected across cities including Mumbai, Tokyo, London, and Sao Paulo. "
    "Co-authors also include representatives from the African Union, ASEAN, and the G20. "
    "The executive summary was drafted by the Geneva-based Institute for Advanced Sustainability Studies."
)                                                        # ~1090 chars → LARGE


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ner_tester() -> NERResponseTest:
    return NERResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, ner_tester):
        assert ner_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, ner_tester):
        assert ner_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, ner_tester):
        assert ner_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, ner_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "x" * ner_tester.small_threshold
        assert ner_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, ner_tester):
        payload_at_boundary = "x" * ner_tester.medium_threshold
        assert ner_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, ner_tester):
        assert ner_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestNERResponses:
    def _assert_valid_ner_response(self, response: dict) -> None:
        assert response["taskType"] == "ner"
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        for item in response["output"]:
            assert "source" in item
            assert "nerPrediction" in item
            assert isinstance(item["nerPrediction"], list)
            for pred in item["nerPrediction"]:
                assert "token" in pred
                assert "tag" in pred
                assert "tokenIndex" in pred
                assert "tokenStartIndex" in pred
                assert "tokenEndIndex" in pred

    def test_small_response_has_valid_structure(self, ner_tester):
        response = ner_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_ner_response(response)

    def test_medium_response_has_valid_structure(self, ner_tester):
        response = ner_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_ner_response(response)

    def test_large_response_has_valid_structure(self, ner_tester):
        response = ner_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_ner_response(response)

    def test_large_response_has_more_entities_than_medium(self, ner_tester):
        medium_preds = ner_tester.get_response(ResponseSize.MEDIUM)["output"][0]["nerPrediction"]
        large_preds  = ner_tester.get_response(ResponseSize.LARGE)["output"][0]["nerPrediction"]
        assert len(large_preds) > len(medium_preds)

    def test_medium_response_has_more_entities_than_small(self, ner_tester):
        small_preds  = ner_tester.get_response(ResponseSize.SMALL)["output"][0]["nerPrediction"]
        medium_preds = ner_tester.get_response(ResponseSize.MEDIUM)["output"][0]["nerPrediction"]
        assert len(medium_preds) > len(small_preds)


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, ner_tester):
        metrics, response = ner_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, ner_tester):
        metrics, response = ner_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, ner_tester):
        metrics, response = ner_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, ner_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = ner_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, ner_tester):
        metrics, _ = ner_tester.run(SMALL_PAYLOAD)
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

    def test_batch_produces_metrics_for_every_request(self, ner_tester):
        results = [ner_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, ner_tester):
        results = [ner_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, ner_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [ner_tester.run(p) for p in batch]

        print("\n" + "=" * 50)
        print("NER Load Simulation — Batch Summary")
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
        assert "NER Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python ner_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = NERResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 55)
    print("NER Response-Size Load Testing — Demo Run")
    print("=" * 55)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        entity_count = len(response["output"][0]["nerPrediction"])
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Entities in response : {entity_count}")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
