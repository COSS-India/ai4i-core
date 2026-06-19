"""Speaker Diarization response-size load testing framework.

Simulates inference latency for the Speaker Diarization service using
pre-defined responses — no model is invoked.  Three response sizes are tested
(SMALL, MEDIUM, LARGE) driven by input payload length.

The endpoint receives base64-encoded audio as input.  Payload size is therefore
the length of the base64 string, which correlates with audio duration.  Sample
payloads below are minimal base64 strings that hit each size bucket; in real
testing, swap them for actual base64 audio content.

Key structural differences from other services:
  - "taskType" is present: "speaker-diarization"
  - Output item contains "total_segments", "num_speakers", "speakers", "segments"
  - Each segment has "start_time", "end_time", "duration", "speaker"
    (no "confidence" — unlike Language Diarization)
  - "speakers" is a deduplicated list of speaker IDs; len must equal num_speakers
  - "config" has "serviceId" (populated) and "language" (null)
  - "smr_response" is absent entirely (not present in the response)

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/speaker_diarization_response_test.py -v

Or run the module directly for a live console report:

    python response_test/speaker_diarization_response_test.py
"""

import sys
import os
import base64
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.speaker_diarization_responses import (
    SMALL_SPEAKER_DIARIZATION_RESPONSE,
    MEDIUM_SPEAKER_DIARIZATION_RESPONSE,
    LARGE_SPEAKER_DIARIZATION_RESPONSE,
)


# ---------------------------------------------------------------------------
# Speaker Diarization tester
# ---------------------------------------------------------------------------

class SpeakerDiarizationResponseTest(BaseResponseTest):
    """Load-test harness for Speaker Diarization inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_SPEAKER_DIARIZATION_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_SPEAKER_DIARIZATION_RESPONSE,
        ResponseSize.LARGE:  LARGE_SPEAKER_DIARIZATION_RESPONSE,
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
def sd_tester() -> SpeakerDiarizationResponseTest:
    return SpeakerDiarizationResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, sd_tester):
        assert sd_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, sd_tester):
        assert sd_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, sd_tester):
        assert sd_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, sd_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "A" * sd_tester.small_threshold
        assert sd_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, sd_tester):
        payload_at_boundary = "A" * sd_tester.medium_threshold
        assert sd_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, sd_tester):
        assert sd_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestSpeakerDiarizationResponses:
    def _assert_valid_sd_response(self, response: dict) -> None:
        assert "taskType" in response
        assert response["taskType"] == "speaker-diarization"
        assert "output" in response
        assert "config" in response
        # smr_response is absent — the route does not include it
        assert "smr_response" not in response
        assert isinstance(response["output"], list)
        assert len(response["output"]) > 0
        config = response["config"]
        assert config is not None
        assert "serviceId" in config
        assert "language" in config
        output_item = response["output"][0]
        assert "total_segments" in output_item
        assert "num_speakers" in output_item
        assert "speakers" in output_item
        assert "segments" in output_item
        assert isinstance(output_item["total_segments"], int)
        assert isinstance(output_item["num_speakers"], int)
        assert isinstance(output_item["speakers"], list)
        assert isinstance(output_item["segments"], list)
        assert output_item["total_segments"] == len(output_item["segments"])
        assert output_item["num_speakers"] == len(output_item["speakers"])
        for segment in output_item["segments"]:
            assert "start_time" in segment
            assert "end_time" in segment
            assert "duration" in segment
            assert "speaker" in segment
            assert isinstance(segment["start_time"], float)
            assert isinstance(segment["end_time"], float)
            assert isinstance(segment["duration"], float)
            assert isinstance(segment["speaker"], str)
            assert segment["end_time"] > segment["start_time"]
            # speaker must be one of the declared speakers
            assert segment["speaker"] in output_item["speakers"]

    def test_small_response_has_valid_structure(self, sd_tester):
        response = sd_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_sd_response(response)

    def test_medium_response_has_valid_structure(self, sd_tester):
        response = sd_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_sd_response(response)

    def test_large_response_has_valid_structure(self, sd_tester):
        response = sd_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_sd_response(response)

    def test_tasktype_is_speaker_diarization(self, sd_tester):
        for size in ResponseSize:
            response = sd_tester.get_response(size)
            assert response["taskType"] == "speaker-diarization"

    def test_total_segments_matches_segment_list_length(self, sd_tester):
        for size in ResponseSize:
            output_item = sd_tester.get_response(size)["output"][0]
            assert output_item["total_segments"] == len(output_item["segments"])

    def test_num_speakers_matches_speakers_list_length(self, sd_tester):
        for size in ResponseSize:
            output_item = sd_tester.get_response(size)["output"][0]
            assert output_item["num_speakers"] == len(output_item["speakers"])

    def test_segment_duration_matches_time_range(self, sd_tester):
        for size in ResponseSize:
            for segment in sd_tester.get_response(size)["output"][0]["segments"]:
                expected = round(segment["end_time"] - segment["start_time"], 6)
                assert abs(segment["duration"] - expected) < 0.01, (
                    f"duration {segment['duration']} != end-start "
                    f"({segment['end_time']} - {segment['start_time']} = {expected})"
                )

    def test_all_segment_speakers_are_in_speakers_list(self, sd_tester):
        for size in ResponseSize:
            output_item = sd_tester.get_response(size)["output"][0]
            declared = set(output_item["speakers"])
            for segment in output_item["segments"]:
                assert segment["speaker"] in declared

    def test_segment_count_increases_with_payload_size(self, sd_tester):
        small_count = sd_tester.get_response(ResponseSize.SMALL)["output"][0]["total_segments"]
        large_count = sd_tester.get_response(ResponseSize.LARGE)["output"][0]["total_segments"]
        assert large_count > small_count

    def test_config_language_is_null(self, sd_tester):
        for size in ResponseSize:
            response = sd_tester.get_response(size)
            assert response["config"]["language"] is None

    def test_smr_response_absent(self, sd_tester):
        for size in ResponseSize:
            assert "smr_response" not in sd_tester.get_response(size)


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, sd_tester):
        metrics, response = sd_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, sd_tester):
        metrics, response = sd_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, sd_tester):
        metrics, response = sd_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, sd_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = sd_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, sd_tester):
        metrics, _ = sd_tester.run(SMALL_PAYLOAD)
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

    def test_batch_produces_metrics_for_every_request(self, sd_tester):
        results = [sd_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, sd_tester):
        results = [sd_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, sd_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [sd_tester.run(p) for p in batch]

        print("\n" + "=" * 55)
        print("Speaker Diarization Load Simulation — Batch Summary")
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
        assert "Speaker Diarization Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python speaker_diarization_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = SpeakerDiarizationResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 58)
    print("Speaker Diarization Response-Size Load Testing — Demo Run")
    print("=" * 58)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        output_item = response["output"][0]
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Total segments    : {output_item['total_segments']}")
        print(f"Speakers          : {output_item['num_speakers']}  {output_item['speakers']}")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
