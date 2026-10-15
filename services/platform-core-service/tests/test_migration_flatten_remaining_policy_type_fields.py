"""Unit tests for the policy_fields flattening migration (a9d4f2b6c8e1).

Only the pure flatten() is tested here; upgrade() is a SELECT plus one UPDATE
per changed row around it.
"""

import importlib.util
from pathlib import Path

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "databases"
    / "migrations"
    / "postgres"
    / "alembic"
    / "versions"
    / "ai4iplatform_core"
    / "a9d4f2b6c8e1_flatten_remaining_policy_type_fields.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("flatten_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


flatten = _load().flatten

PAN = {"entity_name": "PAN", "examples": ["a", "b", "c"], "regex": r"\b[A-Z]{5}\d{4}[A-Z]\b"}
PHONE = {"entity_name": "PHONE", "examples": ["a", "b", "c"], "regex": r"\b\d{10}\b"}
STUDENT = {"entity_name": "STUDENT_ID", "examples": ["a", "b", "c"], "regex": r"\bSTU\d{4}\b"}


def test_domain_sections_are_merged():
    fields = {
        "Finance": {"custom_field": [PAN, PHONE]},
        "Education": {"custom_field": [STUDENT, PHONE]},     # PHONE repeated
    }
    assert flatten(fields) == {"custom_field": [PAN, PHONE, STUDENT]}


def test_model_entities_are_merged_per_language():
    fields = {
        "Finance": {"model_supported_field": [{"en": [{"entity_name": "PERSON"}]}]},
        "Healthcare": {"model_supported_field": [
            {"en": [{"entity_name": "PERSON"}, {"entity_name": "EMAIL_ADDRESS"}]},
            {"hi": [{"entity_name": "PHONE_NUMBER"}]},
        ]},
    }
    assert flatten(fields) == {"model_supported_field": [{
        "en": [{"entity_name": "PERSON"}, {"entity_name": "EMAIL_ADDRESS"}],
        "hi": [{"entity_name": "PHONE_NUMBER"}],
    }]}


def test_top_level_fields_and_domains_are_combined():
    fields = {"custom_field": [PAN], "Education": {"custom_field": [STUDENT]}}
    assert flatten(fields) == {"custom_field": [PAN, STUDENT]}


def test_entity_names_are_trimmed():
    fields = {"custom_field": [{**PAN, "entity_name": " PAN​"}],
              "model_supported_field": [{"en": [{"entity_name": "\tPERSON "}]}]}
    assert flatten(fields) == {"custom_field": [PAN],
                               "model_supported_field": [{"en": [{"entity_name": "PERSON"}]}]}


@pytest.mark.parametrize("fields", [
    {},
    {"custom_field": [PAN]},
    {"custom_field": [PAN], "model_supported_field": [{"en": [{"entity_name": "PERSON"}]}]},
    {"custom_field": [], "model_supported_field": []},
])
def test_flat_rows_are_unchanged(fields):
    assert flatten(fields) == fields


def test_null_lists_become_empty():
    assert flatten({"custom_field": None, "model_supported_field": None}) == {
        "custom_field": [], "model_supported_field": []}


@pytest.mark.parametrize("fields", [
    "oops",
    {"Finance": "oops"},
    {"Finance": {"custom_fields": [PAN]}},                     # unknown key inside a domain
    {"Finance": {"Retail": {"custom_field": [PAN]}}},          # nested two deep
    {"custom_field": "oops"},
    {"custom_field": [{"entity_name": "X"}]},                  # no regex
    {"custom_field": [{"entity_name": "  ", "regex": "a"}]},   # blank after trimming
    {"custom_field": [{"entity_name": 5, "regex": "a"}]},
    {"model_supported_field": [{"en": [{"name": "PERSON"}]}]},
    {"model_supported_field": [{"en": "PERSON"}]},
])
def test_unconvertible_rows_are_left_for_a_person(fields):
    assert flatten(fields) is None
