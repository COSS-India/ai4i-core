"""
Unit tests: PII policy simulation (POST /pii/simulate), the entity_counter
anonymizer, request validation on the /pii routes, and language detection.

spaCy is not loaded. The analyzer is replaced with a fake that really runs
the ad-hoc recognizers it is given and honours the entity list and
language, plus fixed "model" detections standing in for spaCy NER. The
anonymizer, the custom operator, and route validation are the real ones.
"""

import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from presidio_analyzer import RecognizerResult

import services.pii.engine as engine_module
from app_factory import _setup_exception_handlers
import services.pii.simulation as simulation
from routes.pii import MAX_SIMULATE_TEXT_LEN, router
from services.pii.language import detect_language
from services.pii.model_registry import get_spacy_lang_code
from services.pii.operators import InstanceCounterAnonymizer
from services.pii.simulation import (
    CustomField,
    InvalidPolicyError,
    PolicyType,
    RegexTimeoutError,
    simulate,
)

FINANCE = PolicyType(
    name="Finance-PII",
    custom_fields=[
        CustomField("BANK_ACCOUNT_NUMBER", r"\b\d{9,18}\b"),
        CustomField("IFSC_CODE", r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
        CustomField("PAN_NUMBER", r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    ],
)


class FakeAnalyzer:
    """Stands in for Presidio's AnalyzerEngine without spaCy."""

    def __init__(self, model_hits=None):
        # {entity_type: [substring, ...]} the "NER model" finds
        self.model_hits = model_hits or {}
        self.calls = []

    def analyze(self, text, language, entities=None, ad_hoc_recognizers=None):
        self.calls.append({"language": language, "entities": entities})
        results = []
        for rec in ad_hoc_recognizers or []:
            if rec.supported_language != language:
                continue
            if entities is not None and rec.supported_entities[0] not in entities:
                continue
            results.extend(rec.analyze(text, entities))
        for entity, values in self.model_hits.items():
            if entities is not None and entity not in entities:
                continue
            for value in values:
                start = text.find(value)
                if start >= 0:
                    results.append(RecognizerResult(entity, start, start + len(value), 0.85))
        return results


@pytest.fixture
def fake_engine():
    """A real PresidioEngine (real anonymizer + operator) over FakeAnalyzer."""
    fake = FakeAnalyzer()

    class _Provider:
        def __init__(self, *a, **k):
            pass

        def create_engine(self):
            return None

    with patch.object(engine_module, "NlpEngineProvider", _Provider), \
         patch.object(engine_module, "AnalyzerEngine", lambda *a, **k: fake):
        engine = engine_module.PresidioEngine()
    with patch.object(simulation, "get_engine", lambda: engine):
        yield fake


# ── entity_counter operator ──────────────────────────────────────────────────


def test_operator_numbers_per_type_and_reuses_tokens():
    op = InstanceCounterAnonymizer()
    mapping = {}
    tokens = [
        op.operate(value, {"entity_type": etype, "entity_mapping": mapping})
        for etype, value in [("PERSON", "Alice"), ("PERSON", "Bob"),
                             ("EMAIL_ADDRESS", "a@x.com"), ("PERSON", "Alice")]
    ]
    assert tokens == ["<PERSON_1>", "<PERSON_2>", "<EMAIL_ADDRESS_1>", "<PERSON_1>"]
    assert mapping == {
        "PERSON": {"Alice": "<PERSON_1>", "Bob": "<PERSON_2>"},
        "EMAIL_ADDRESS": {"a@x.com": "<EMAIL_ADDRESS_1>"},
    }


def test_operator_requires_entity_mapping():
    with pytest.raises(ValueError):
        InstanceCounterAnonymizer().validate({})


# ── simulate() ───────────────────────────────────────────────────────────────


def test_simulate_replaces_each_policy_entity(fake_engine):
    text = "Account 123456789012, IFSC SBIN0000456, PAN ABCDE1234F."
    result = simulate(text, [FINANCE])

    assert result.sanitized_text == (
        "Account <BANK_ACCOUNT_NUMBER_1>, IFSC <IFSC_CODE_1>, PAN <PAN_NUMBER_1>."
    )
    assert [(d.entity_type, d.policy_type, d.instances, d.replacements) for d in result.detected] == [
        ("BANK_ACCOUNT_NUMBER", "Finance-PII", 1, {"123456789012": "<BANK_ACCOUNT_NUMBER_1>"}),
        ("IFSC_CODE", "Finance-PII", 1, {"SBIN0000456": "<IFSC_CODE_1>"}),
        ("PAN_NUMBER", "Finance-PII", 1, {"ABCDE1234F": "<PAN_NUMBER_1>"}),
    ]


def test_simulate_only_asks_for_the_policys_entities(fake_engine):
    simulate("PAN ABCDE1234F", [FINANCE])
    assert fake_engine.calls[-1]["entities"] == ["BANK_ACCOUNT_NUMBER", "IFSC_CODE", "PAN_NUMBER"]


def test_repeated_value_counts_instances_and_keeps_one_token(fake_engine):
    result = simulate("PAN ABCDE1234F and again ABCDE1234F", [FINANCE])
    assert result.sanitized_text == "PAN <PAN_NUMBER_1> and again <PAN_NUMBER_1>"
    (row,) = result.detected
    assert row.instances == 2
    assert row.replacements == {"ABCDE1234F": "<PAN_NUMBER_1>"}


def test_custom_regex_is_case_sensitive(fake_engine):
    # Presidio's default flags include IGNORECASE; policy regexes must not.
    result = simulate("ifsc sbin0000456 and pan abcde1234f", [FINANCE])
    assert result.detected == []


def test_policy_without_entities_detects_nothing(fake_engine):
    # entities=[] means "every entity" to Presidio, so the analyzer must not run.
    result = simulate("Alice lives here", [PolicyType(name="Empty")])
    assert result.sanitized_text == "Alice lives here"
    assert result.detected == []
    assert fake_engine.calls == []


def test_model_entities_use_the_detected_language(fake_engine):
    fake_engine.model_hits = {"PERSON": ["Alice", "राहुल"]}
    policy = PolicyType(name="Names", model_entities={"en": ["PERSON"], "hi": ["EMAIL_ADDRESS"]})

    en = simulate("Please contact Alice about the invoice.", [policy])
    assert en.sanitized_text == "Please contact <PERSON_1> about the invoice."
    assert fake_engine.calls[-1]["language"] == "en"

    # Hindi text: the policy's "hi" list has no PERSON, so the name stays.
    hi = simulate("मेरा नाम राहुल है और मैं दिल्ली में रहता हूँ", [policy])
    assert hi.detected == []
    assert fake_engine.calls[-1]["entities"] == ["EMAIL_ADDRESS"]


def test_invalid_regex_raises_invalid_policy(fake_engine):
    bad = PolicyType(name="Bad", custom_fields=[CustomField("X", "(")])
    with pytest.raises(InvalidPolicyError, match="Bad: invalid regex for X"):
        simulate("anything", [bad])


def test_catastrophic_regex_is_cut_off(fake_engine):
    evil = PolicyType(name="Evil", custom_fields=[CustomField("X", r"(a|aa)+$")])
    with patch.object(simulation, "REGEX_TIMEOUT_SECONDS", 0.2):
        started = time.monotonic()
        with pytest.raises(RegexTimeoutError, match="Evil:X"):
            simulate("a" * 40 + "!", [evil])
    assert time.monotonic() - started < 5


# ── route validation (400, not 500) ──────────────────────────────────────────


@pytest.fixture
def client():
    # The service's real handlers: request validation errors become 400.
    app = FastAPI()
    _setup_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize("policy_fields", [
    {"custom_field": "oops"},
    {"custom_field": [{"entity_name": 5, "regex": "a"}]},
    {"custom_field": [{"entity_name": "X"}]},
    {"custom_field": [{"entity_name": "X", "regex": "   "}]},
    {"custom_field": [{"entity_name": "   ", "regex": "a"}]},
    {"model_supported_field": {"en": []}},
    {"model_supported_field": [{"en": ["PERSON"]}]},
])
def test_simulate_rejects_malformed_policy_fields(client, policy_fields):
    resp = client.post("/pii/simulate", json={
        "text": "abc", "policyTypes": [{"policy_type": "X", "policy_fields": policy_fields}],
    })
    assert resp.status_code == 400


def test_simulate_rejects_text_over_the_limit(client):
    resp = client.post("/pii/simulate", json={
        "text": "a" * (MAX_SIMULATE_TEXT_LEN + 1), "policyTypes": [],
    })
    assert resp.status_code == 400


def test_simulate_maps_invalid_regex_to_400(client, fake_engine):
    resp = client.post("/pii/simulate", json={
        "text": "abc",
        "policyTypes": [{"policy_type": "Bad", "policy_fields": {
            "custom_field": [{"entity_name": "X", "regex": "(", "examples": ["a", "b", "c"]}]}}],
    })
    assert resp.status_code == 400
    assert "Bad: invalid regex for X" in resp.json()["detail"]


def test_simulate_accepts_platform_core_rows_with_extra_keys(client, fake_engine):
    resp = client.post("/pii/simulate", json={
        "text": "PAN ABCDE1234F",
        "policyTypes": [{"id": 2, "policy_type": "Finance-PII", "policy_fields": {
            "handling": "mask", "implementation_method": "regex",
            "custom_field": [{"entity_name": "PAN_NUMBER", "regex": r"\b[A-Z]{5}\d{4}[A-Z]\b",
                              "examples": ["ABCDE1234F", "PQRSX5678K", "LMNOP4321Z"],
                              "mode": "mask"}]}}],
    })
    assert resp.status_code == 200
    assert resp.json()["sanitizedText"] == "PAN <PAN_NUMBER_1>"


@pytest.mark.parametrize("span", [
    {"start": 2, "end": 50},    # past the end of the text: Presidio raises (500)
    {"start": 2, "end": 1},     # start > end: Presidio duplicates text
    {"start": 1, "end": 1},     # empty span
    {"start": True, "end": 2},  # lax mode would read true as 1
    {"start": "1", "end": 2},
    {"start": -1, "end": 2},
])
def test_anonymize_rejects_bad_spans(client, span):
    resp = client.post("/pii/anonymize", json={
        "text": "abc", "analyzerResults": [{"entityType": "X", "score": 1.0, **span}],
    })
    assert resp.status_code == 400


# ── language detection ───────────────────────────────────────────────────────


@pytest.mark.parametrize("text, expected", [
    ("Please contact Alice about the invoice.", "en"),
    ("मेरा नाम राहुल है और मैं दिल्ली में रहता हूँ", "hi"),
    ("123456789012", "en"),   # nothing to detect from: fallback
    ("", "en"),
])
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_detected_language_maps_to_spacy_pipeline():
    assert get_spacy_lang_code("en") == "en"
    assert get_spacy_lang_code("hi") == "xx"
