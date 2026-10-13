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
from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.predefined_recognizers import SpacyRecognizer

import services.pii.engine as engine_module
from app_factory import _setup_exception_handlers
import services.pii.simulation as simulation
from routes.pii import MAX_CUSTOM_FIELDS, MAX_MODEL_ENTITIES, MAX_SIMULATE_TEXT_LEN, router
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


class FakeRegistry:
    """Like Presidio's registry for en and xx: spaCy NER plus pattern
    recognizers for email and phone. No IN_PAN / IN_AADHAAR."""

    def get_recognizers(self, language, all_fields=False):
        return [
            SpacyRecognizer(supported_language=language, supported_entities=["PERSON", "LOCATION"]),
            PatternRecognizer(supported_entity="EMAIL_ADDRESS", supported_language=language,
                              patterns=[Pattern("email", "@", 0.5)]),
            PatternRecognizer(supported_entity="PHONE_NUMBER", supported_language=language,
                              patterns=[Pattern("phone", r"\d{10}", 0.5)]),
        ]


class FakeAnalyzer:
    """Stands in for Presidio's AnalyzerEngine without spaCy."""

    def __init__(self, model_hits=None):
        # {entity_type: [substring, ...]} the built-in recognizers find
        self.model_hits = model_hits or {}
        self.calls = []
        self.registry = FakeRegistry()

    def analyze(self, text, language, entities=None):
        self.calls.append({"language": language, "entities": entities})
        results = []
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
    with patch.object(simulation, "get_engine", lambda: engine), \
         patch.object(engine_module, "get_engine", lambda: engine):
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
    assert [(d.entity_type, d.policy_types, d.instances, d.replacements) for d in result.detected] == [
        ("BANK_ACCOUNT_NUMBER", ["Finance-PII"], 1, {"123456789012": "<BANK_ACCOUNT_NUMBER_1>"}),
        ("IFSC_CODE", ["Finance-PII"], 1, {"SBIN0000456": "<IFSC_CODE_1>"}),
        ("PAN_NUMBER", ["Finance-PII"], 1, {"ABCDE1234F": "<PAN_NUMBER_1>"}),
    ]


def test_regex_only_policy_does_not_call_presidio(fake_engine):
    # Policy regexes run on their own; Presidio (and spaCy) only run for
    # model_supported_field entities.
    simulate("PAN ABCDE1234F", [FINANCE])
    assert fake_engine.calls == []


def test_policy_regex_wins_a_tie_with_a_builtin(fake_engine):
    # EmailRecognizer scores a valid address 1.0, the same as a policy regex.
    # With both on one span Presidio may keep either; the policy's match must
    # not be lost, so built-ins are not asked for regex-only entities at all.
    fake_engine.model_hits = {"EMAIL_ADDRESS": ["arjun@college.edu"]}
    email = CustomField("EMAIL_ADDRESS", r"\b[\w.]+@[\w.]+\.[a-z]{2,}\b")
    result = simulate("Write to arjun@college.edu today", [PolicyType("PII", [email])])
    assert result.sanitized_text == "Write to <EMAIL_ADDRESS_1> today"
    assert fake_engine.calls == []


@pytest.mark.parametrize("text, model_entities, missing", [
    ("Aadhaar 1234 5678 9012", {"en": ["IN_AADHAAR"]}, "IN_AADHAAR"),         # no recognizer
    ("मेरा नाम राहुल शर्मा है, मैं दिल्ली में रहता हूँ", {"hi": ["PERSON"]}, "PERSON"),  # no Hindi NER
])
def test_undetectable_model_entities_are_rejected(fake_engine, text, model_entities, missing):
    with pytest.raises(InvalidPolicyError, match=f"cannot be detected .*{missing}"):
        simulate(text, [PolicyType("PII", model_entities=model_entities)])
    assert fake_engine.calls == []


def test_detectable_entities_per_language(fake_engine):
    engine = simulation.get_engine()
    assert {"PERSON", "EMAIL_ADDRESS"} <= engine.detectable_entities("en")
    assert {"PERSON", "EMAIL_ADDRESS"} <= engine.detectable_entities("fr")   # WikiNER language
    hindi = engine.detectable_entities("hi")
    assert "EMAIL_ADDRESS" in hindi and "PERSON" not in hindi


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


def test_custom_only_entity_ignores_builtin_recognizers(fake_engine):
    # Presidio's PhoneRecognizer also supports PHONE_NUMBER; the policy's own
    # regex (10 digits in a row) does not match "+91 98765 43210".
    fake_engine.model_hits = {"PHONE_NUMBER": ["+91 98765 43210"]}
    phone = CustomField("PHONE_NUMBER", r"\b(?:\+?\d{1,3}[\s-]?)?\d{10}\b")

    custom_only = simulate("Call +91 98765 43210", [PolicyType("PII", [phone])])
    assert custom_only.detected == []

    # Listed in model_supported_field too: the built-in match is wanted.
    both = simulate("Call +91 98765 43210", [
        PolicyType("PII", [phone], model_entities={"en": ["PHONE_NUMBER"]})])
    assert both.sanitized_text == "Call <PHONE_NUMBER_1>"


def test_entity_defined_by_two_policy_types_lists_both(fake_engine):
    a = PolicyType("Contact", [CustomField("EMAIL_ADDRESS", r"\b\w+@college\.edu\b")])
    b = PolicyType("PII", [CustomField("EMAIL_ADDRESS", r"\b\w+@acme\.com\b")])
    result = simulate("arjun@college.edu and bob@acme.com", [a, b])
    (row,) = result.detected
    assert row.policy_types == ["Contact", "PII"]
    assert row.instances == 2


def test_invalid_regex_raises_invalid_policy(fake_engine):
    bad = PolicyType(name="Bad", custom_fields=[CustomField("X", "(")])
    with pytest.raises(InvalidPolicyError, match="Bad: invalid regex for X"):
        simulate("anything", [bad])


def test_catastrophic_regex_is_cut_off(fake_engine):
    evil = PolicyType(name="Evil", custom_fields=[CustomField("X", r"(a|aa)+$")])
    with patch.object(simulation, "REGEX_BUDGET_SECONDS", 0.2):
        started = time.monotonic()
        with pytest.raises(RegexTimeoutError, match="Evil:X"):
            simulate("a" * 40 + "!", [evil])
    assert time.monotonic() - started < 5


def test_regex_budget_is_per_request_not_per_pattern(fake_engine):
    # 20 fast patterns, each well under the budget on its own; a fake clock
    # advances 0.1s per check. A shared budget of 1s must run out partway
    # through, which a per-pattern limit never would.
    clock = iter(i * 0.1 for i in range(1000))
    many = PolicyType(name="Many", custom_fields=[
        CustomField(f"X{i}", r"a") for i in range(20)
    ])
    with patch.object(simulation, "REGEX_BUDGET_SECONDS", 1.0), \
         patch.object(simulation.time, "monotonic", lambda: next(clock)):
        with pytest.raises(RegexTimeoutError, match="1.0s in total"):
            simulate("a", [many])


def test_language_falls_back_to_policy_languages(fake_engine):
    # langdetect alone reads this as "et"; the policy only lists "en".
    assert detect_language("Email arjun@college.edu") == "et"
    fake_engine.model_hits = {"EMAIL_ADDRESS": ["arjun@college.edu"]}
    policy = PolicyType(name="Contact", model_entities={"en": ["EMAIL_ADDRESS"]})

    result = simulate("Email arjun@college.edu", [policy])
    assert result.sanitized_text == "Email <EMAIL_ADDRESS_1>"
    assert fake_engine.calls[-1]["language"] == "en"


# ── route validation (400, not 500) ──────────────────────────────────────────


@pytest.fixture
def client():
    # The service's real handlers: request validation errors become 400.
    app = FastAPI()
    _setup_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


def _simulate_body(policy_fields, text="abc"):
    return {
        "text": text,
        "policyTypes": [{"policy_type": "PII", "policy_fields": policy_fields}],
    }


PAN_FIELD = {"entity_name": "PAN_NUMBER", "regex": r"\b[A-Z]{5}\d{4}[A-Z]\b",
             "examples": ["ABCDE1234F", "PQRSX5678K", "LMNOP4321Z"]}
STUDENT_ID_FIELD = {"entity_name": "STUDENT_ID", "regex": r"\bSTU\d{4}\b",
                    "examples": ["STU1234", "STU5678", "STU9012"]}


@pytest.mark.parametrize("domain_fields", [
    {"custom_field": "oops"},
    {"custom_field": [{"entity_name": 5, "regex": "a"}]},
    {"custom_field": [{"entity_name": "X"}]},
    {"custom_field": [{"entity_name": "X", "regex": "   "}]},
    {"custom_field": [{"entity_name": "   ", "regex": "a"}]},
    {"custom_field": [{"entity_name": "\u200b", "regex": "a"}]},       # invisible only
    {"custom_field": [{"entity_name": " \ufeff\u2060 ", "regex": "a"}]},
    {"model_supported_field": {"en": []}},
    {"model_supported_field": [{"en": ["PERSON"]}]},
    {"custom_fields": [PAN_FIELD]},                                    # typo: unknown key
])
def test_simulate_rejects_malformed_policy_fields(client, domain_fields):
    resp = client.post("/pii/simulate", json=_simulate_body({"Finance": domain_fields}))
    assert resp.status_code == 400


def test_simulate_rejects_the_flat_policy_fields_shape(client):
    # The pre-#1738 shape: must be a 400, not an empty "no PII" result.
    resp = client.post("/pii/simulate", json=_simulate_body({"custom_field": [PAN_FIELD]}))
    assert resp.status_code == 400


def test_simulate_applies_every_domain_sent(client, fake_engine):
    fields = {"Finance": {"custom_field": [PAN_FIELD]},
              "Education": {"custom_field": [STUDENT_ID_FIELD]}}
    resp = client.post("/pii/simulate", json=_simulate_body(
        fields, text="PAN ABCDE1234F, student STU1234"))
    assert resp.status_code == 200
    assert resp.json()["sanitizedText"] == "PAN <PAN_NUMBER_1>, student <STUDENT_ID_1>"


def test_simulate_rejects_text_over_the_limit(client):
    resp = client.post("/pii/simulate", json=_simulate_body(
        {}, text="a" * (MAX_SIMULATE_TEXT_LEN + 1)))
    assert resp.status_code == 400


def test_simulate_maps_invalid_regex_to_400(client, fake_engine):
    resp = client.post("/pii/simulate", json=_simulate_body({"Finance": {"custom_field": [
        {"entity_name": "X", "regex": "(", "examples": ["a", "b", "c"]}]}}))
    assert resp.status_code == 400
    assert "PII: invalid regex for X" in resp.json()["detail"]


def test_simulate_accepts_platform_core_rows(client, fake_engine):
    # A row as #1738 stores it; entries carry examples (and may carry mode).
    resp = client.post("/pii/simulate", json={
        "text": "PAN ABCDE1234F",
        "policyTypes": [{"id": 1, "policy_type": "PII", "policy_fields": {
            "Finance": {"custom_field": [{**PAN_FIELD, "mode": "mask"}]}}}],
    })
    assert resp.status_code == 200
    assert resp.json()["sanitizedText"] == "PAN <PAN_NUMBER_1>"


def test_simulate_caps_custom_fields_per_request(client):
    # 3 policy types, each list under its own cap; the total is over.
    per_type = MAX_CUSTOM_FIELDS // 2 + 1
    field = {"entity_name": "X", "regex": "a"}
    body = {"text": "abc", "policyTypes": [
        {"policy_type": f"T{i}", "policy_fields": {"D": {"custom_field": [field] * per_type}}}
        for i in range(3)
    ]}
    resp = client.post("/pii/simulate", json=body)
    assert resp.status_code == 400
    assert f"at most {MAX_CUSTOM_FIELDS} per request" in resp.json()["detail"]


def test_simulate_caps_model_entities_per_request(client):
    entities = [{"entity_name": "PERSON"}] * (MAX_MODEL_ENTITIES // 2 + 1)
    body = {"text": "abc", "policyTypes": [
        {"policy_type": f"T{i}", "policy_fields": {"D": {"model_supported_field": [{"en": entities}]}}}
        for i in range(3)
    ]}
    resp = client.post("/pii/simulate", json=body)
    assert resp.status_code == 400
    assert f"at most {MAX_MODEL_ENTITIES} per request" in resp.json()["detail"]


def test_simulate_response_lists_policy_types(client, fake_engine):
    resp = client.post("/pii/simulate", json=_simulate_body({"Finance": {"custom_field": [PAN_FIELD]}},
                                                            text="PAN ABCDE1234F"))
    assert resp.json()["detected"][0]["policyTypes"] == ["PII"]


def test_anonymize_with_supplied_analyzer_results(client, fake_engine):
    # /analyze-shaped results go straight to the real anonymizer + entity_counter.
    text = "Alice met Bob, then Alice left"
    resp = client.post("/pii/anonymize", json={
        "text": text,
        "analyzerResults": [
            {"entityType": "PERSON", "start": 0, "end": 5, "score": 0.85},
            {"entityType": "PERSON", "start": 10, "end": 13, "score": 0.85},
            {"entityType": "PERSON", "start": 20, "end": 25, "score": 0.85},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    # Presidio replaces right to left, so the later name is numbered first.
    assert body["anonymizedText"] == "<PERSON_1> met <PERSON_2>, then <PERSON_1> left"
    assert body["entityMapping"] == {"PERSON": {"Alice": "<PERSON_1>", "Bob": "<PERSON_2>"}}
    assert [(i["entityType"], i["text"], i["operator"]) for i in body["items"]] == [
        ("PERSON", "<PERSON_1>", "entity_counter"),
        ("PERSON", "<PERSON_2>", "entity_counter"),
        ("PERSON", "<PERSON_1>", "entity_counter"),
    ]
    assert fake_engine.calls == []   # supplied results: no analysis


def test_simulate_undetectable_model_entity_is_400_not_500(client, fake_engine):
    resp = client.post("/pii/simulate", json=_simulate_body(
        {"Healthcare": {"model_supported_field": [{"en": [{"entity_name": "IN_AADHAAR"}]}]}},
        text="Aadhaar 1234 5678 9012"))
    assert resp.status_code == 400
    assert "IN_AADHAAR" in resp.json()["detail"]


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


@pytest.mark.parametrize("text, candidates, expected", [
    ("Email arjun@college.edu", {"en", "hi"}, "en"),                      # misread as "et"
    ("Patient Meena Raj, Aadhaar 1234 5678 9012", {"en"}, "en"),         # misread as "nl"
    ("मेरा नाम राहुल है और मैं दिल्ली में रहता हूँ", {"en", "hi"}, "hi"),
    ("मेरा नाम राहुल है और मैं दिल्ली में रहता हूँ", {"en"}, "en"),
])
def test_detect_language_among_candidates(text, candidates, expected):
    assert detect_language(text, candidates) == expected


def test_detected_language_maps_to_spacy_pipeline():
    assert get_spacy_lang_code("en") == "en"
    assert get_spacy_lang_code("hi") == "xx"
