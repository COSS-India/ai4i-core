"""TTS response-size load testing framework.

Simulates inference latency for the TTS service using pre-defined
responses — no model is invoked.  Three response sizes are tested (SMALL,
MEDIUM, LARGE) driven by input text length.

Key structural differences from other inference services:
  - Response uses "audio" key instead of "output"
  - "config" is fully populated (not null) with language, audioFormat,
    encoding, samplingRate, and audioDuration
  - "audioContent" is a base64-encoded MP3 string
  - "audioUri" is always null
  - "audioDuration" appears in both the audio item and config

Run with pytest (no extra flags needed):

    cd services/inference-service
    pytest response_test/tts_response_test.py -v

Or run the module directly for a live console report:

    python response_test/tts_response_test.py
"""

import sys
import os
import pytest

# Allow imports from response_test without installing as a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from response_test.base_response_test import BaseResponseTest, ResponseSize, InferenceMetrics
from response_test.responses.tts_responses import (
    SMALL_TTS_RESPONSE,
    MEDIUM_TTS_RESPONSE,
    LARGE_TTS_RESPONSE,
)


# ---------------------------------------------------------------------------
# TTS-specific tester
# ---------------------------------------------------------------------------

class TTSResponseTest(BaseResponseTest):
    """Load-test harness for TTS inference responses."""

    _responses = {
        ResponseSize.SMALL:  SMALL_TTS_RESPONSE,
        ResponseSize.MEDIUM: MEDIUM_TTS_RESPONSE,
        ResponseSize.LARGE:  LARGE_TTS_RESPONSE,
    }

    def get_response(self, size: ResponseSize) -> dict:
        return self._responses[size]


# ---------------------------------------------------------------------------
# Sample payloads (Hindi text — the source language configured in responses)
# ---------------------------------------------------------------------------

SMALL_PAYLOAD = "नमस्ते, आज मौसम बहुत अच्छा है।"          # 30 chars  → SMALL

MEDIUM_PAYLOAD = (
    "भारत एक महान देश है जहाँ विभिन्न धर्मों और संस्कृतियों के लोग सद्भाव से रहते हैं। "
    "यहाँ की संस्कृति और परंपरा हज़ारों वर्ष पुरानी और समृद्ध है। "
    "देश में हिंदी, तमिल, तेलुगू, बंगाली समेत सैकड़ों भाषाएँ बोली जाती हैं। "
    "हिंदी राजभाषा के रूप में पूरे देश को जोड़ती है और करोड़ों लोग इसे बोलते और समझते हैं।"
)                                                           # 299 chars → MEDIUM

LARGE_PAYLOAD = (
    "कृत्रिम बुद्धिमत्ता आज के दौर में तकनीक की सबसे महत्वपूर्ण शाखाओं में से एक बन गई है। "
    "इसका उपयोग स्वास्थ्य सेवा, शिक्षा, कृषि, वित्त और अनेक अन्य क्षेत्रों में तेज़ी से बढ़ रहा है। "
    "भारत में भी कृत्रिम बुद्धिमत्ता के क्षेत्र में अनेक महत्वपूर्ण प्रयास हो रहे हैं। "
    "सरकार ने राष्ट्रीय कृत्रिम बुद्धिमत्ता नीति तैयार की है और अनेक सरकारी योजनाओं में इसका उपयोग किया जा रहा है। "
    "देश के स्टार्टअप और बड़ी कंपनियाँ भी इस दिशा में तेज़ी से काम कर रही हैं। "
    "वाक् पहचान तकनीक ने हिंदी सहित अन्य भारतीय भाषाओं में भी उल्लेखनीय प्रगति की है। "
    "अब मशीनें हिंदी, तमिल, तेलुगू, बंगाली जैसी भाषाओं को समझ और बोल सकती हैं। "
    "टेक्स्ट-टू-स्पीच प्रणालियाँ भारतीय भाषाओं में प्राकृतिक और स्पष्ट ध्वनि उत्पन्न करने में सक्षम हो गई हैं। "
    "इससे दृष्टिबाधित लोगों और डिजिटल साक्षरता से दूर लोगों को बहुत लाभ हो रहा है। "
    "प्राकृतिक भाषा प्रसंस्करण के क्षेत्र में कई शोध संस्थान और विश्वविद्यालय सक्रिय रूप से काम कर रहे हैं। "
    "भाषा तकनीक के माध्यम से भारत की विविधता को डिजिटल एकता में बदला जा रहा है। "
    "भविष्य में यह तकनीक और भी अधिक सटीक और प्रभावशाली होगी जिससे करोड़ों भारतीयों को लाभ मिलेगा।"
)                                                           # 1056 chars → LARGE


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tts_tester() -> TTSResponseTest:
    return TTSResponseTest()


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestPayloadClassification:
    def test_small_payload_classifies_as_small(self, tts_tester):
        assert tts_tester.classify_payload(SMALL_PAYLOAD) == ResponseSize.SMALL

    def test_medium_payload_classifies_as_medium(self, tts_tester):
        assert tts_tester.classify_payload(MEDIUM_PAYLOAD) == ResponseSize.MEDIUM

    def test_large_payload_classifies_as_large(self, tts_tester):
        assert tts_tester.classify_payload(LARGE_PAYLOAD) == ResponseSize.LARGE

    def test_boundary_at_small_threshold(self, tts_tester):
        # Exactly at threshold belongs to MEDIUM bucket (< 200 is SMALL)
        payload_at_boundary = "x" * tts_tester.small_threshold
        assert tts_tester.classify_payload(payload_at_boundary) == ResponseSize.MEDIUM

    def test_boundary_at_medium_threshold(self, tts_tester):
        payload_at_boundary = "x" * tts_tester.medium_threshold
        assert tts_tester.classify_payload(payload_at_boundary) == ResponseSize.LARGE

    def test_empty_payload_classifies_as_small(self, tts_tester):
        assert tts_tester.classify_payload("") == ResponseSize.SMALL


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestTTSResponses:
    def _assert_valid_tts_response(self, response: dict) -> None:
        # TTS uses "audio", not "output"
        assert "audio" in response
        assert "config" in response
        assert "smr_response" in response
        assert isinstance(response["audio"], list)
        assert len(response["audio"]) > 0
        assert response["smr_response"] is None
        # config is populated — not null (unlike NER / Language Detection)
        config = response["config"]
        assert config is not None
        assert "language" in config
        assert "audioFormat" in config
        assert "encoding" in config
        assert "samplingRate" in config
        assert "audioDuration" in config
        assert config["language"]["sourceLanguage"] is not None
        for item in response["audio"]:
            assert "audioContent" in item
            assert "audioUri" in item
            assert "audioDuration" in item
            assert isinstance(item["audioContent"], str)
            assert item["audioUri"] is None
            assert isinstance(item["audioDuration"], float)
            assert item["audioDuration"] > 0

    def test_small_response_has_valid_structure(self, tts_tester):
        response = tts_tester.get_response(ResponseSize.SMALL)
        self._assert_valid_tts_response(response)

    def test_medium_response_has_valid_structure(self, tts_tester):
        response = tts_tester.get_response(ResponseSize.MEDIUM)
        self._assert_valid_tts_response(response)

    def test_large_response_has_valid_structure(self, tts_tester):
        response = tts_tester.get_response(ResponseSize.LARGE)
        self._assert_valid_tts_response(response)

    def test_config_audio_duration_matches_audio_item(self, tts_tester):
        for size in ResponseSize:
            response = tts_tester.get_response(size)
            audio_duration = response["audio"][0]["audioDuration"]
            config_duration = response["config"]["audioDuration"]
            assert audio_duration == config_duration, (
                f"{size}: audio[0].audioDuration ({audio_duration}) != "
                f"config.audioDuration ({config_duration})"
            )

    def test_smr_response_is_none(self, tts_tester):
        for size in ResponseSize:
            response = tts_tester.get_response(size)
            assert response["smr_response"] is None

    def test_audio_duration_increases_with_payload_size(self, tts_tester):
        small_dur = tts_tester.get_response(ResponseSize.SMALL)["audio"][0]["audioDuration"]
        medium_dur = tts_tester.get_response(ResponseSize.MEDIUM)["audio"][0]["audioDuration"]
        large_dur = tts_tester.get_response(ResponseSize.LARGE)["audio"][0]["audioDuration"]
        assert small_dur < medium_dur < large_dur


# ---------------------------------------------------------------------------
# Metrics / timing tests
# ---------------------------------------------------------------------------

class TestInferenceMetrics:
    def test_metrics_returned_for_small_payload(self, tts_tester):
        metrics, response = tts_tester.run(SMALL_PAYLOAD)
        assert isinstance(metrics, InferenceMetrics)
        assert metrics.response_size == ResponseSize.SMALL
        assert metrics.payload_size == len(SMALL_PAYLOAD)
        assert metrics.duration_ms >= 0

    def test_metrics_returned_for_medium_payload(self, tts_tester):
        metrics, response = tts_tester.run(MEDIUM_PAYLOAD)
        assert metrics.response_size == ResponseSize.MEDIUM
        assert metrics.payload_size == len(MEDIUM_PAYLOAD)

    def test_metrics_returned_for_large_payload(self, tts_tester):
        metrics, response = tts_tester.run(LARGE_PAYLOAD)
        assert metrics.response_size == ResponseSize.LARGE
        assert metrics.payload_size == len(LARGE_PAYLOAD)

    def test_duration_is_non_negative(self, tts_tester):
        for payload in (SMALL_PAYLOAD, MEDIUM_PAYLOAD, LARGE_PAYLOAD):
            metrics, _ = tts_tester.run(payload)
            assert metrics.duration_ms >= 0, f"Negative duration for {metrics.response_size}"

    def test_metrics_str_contains_required_fields(self, tts_tester):
        metrics, _ = tts_tester.run(SMALL_PAYLOAD)
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

    def test_batch_produces_metrics_for_every_request(self, tts_tester):
        results = [tts_tester.run(p) for p in self._make_batch()]
        assert len(results) == self.BATCH_SIZE
        for metrics, response in results:
            assert isinstance(metrics, InferenceMetrics)
            assert response is not None

    def test_batch_covers_all_three_response_sizes(self, tts_tester):
        results = [tts_tester.run(p) for p in self._make_batch()]
        sizes_seen = {m.response_size for m, _ in results}
        assert sizes_seen == {ResponseSize.SMALL, ResponseSize.MEDIUM, ResponseSize.LARGE}

    def test_batch_summary_report(self, tts_tester, capsys):
        """Print a human-readable summary — captured by pytest -s."""
        batch = self._make_batch()
        results = [tts_tester.run(p) for p in batch]

        print("\n" + "=" * 50)
        print("TTS Load Simulation — Batch Summary")
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
        assert "TTS Load Simulation" in captured.out


# ---------------------------------------------------------------------------
# Standalone runner (python tts_response_test.py)
# ---------------------------------------------------------------------------

def _standalone_demo():
    tester = TTSResponseTest()
    payloads = [
        ("small",  SMALL_PAYLOAD),
        ("medium", MEDIUM_PAYLOAD),
        ("large",  LARGE_PAYLOAD),
    ]

    print("\n" + "=" * 55)
    print("TTS Response-Size Load Testing — Demo Run")
    print("=" * 55)
    for label, payload in payloads:
        metrics, response = tester.run(payload)
        audio_item = response["audio"][0]
        print(f"\n[{label.upper()} payload]")
        print(metrics)
        print(f"Audio duration    : {audio_item['audioDuration']:.2f} s")
        print(f"Audio content len : {len(audio_item['audioContent'])} chars (base64)")
        print("-" * 40)
    print("\nDone.")


if __name__ == "__main__":
    _standalone_demo()
