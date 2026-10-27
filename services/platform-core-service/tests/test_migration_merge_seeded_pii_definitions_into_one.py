"""Unit tests for the migration that merges the seeded PII definitions (c4e6a8b0d2f4).

The seeded row bypasses the policy-type API, so these check it would pass its
validation on the next edit, and that each regex matches its own examples
(inference matches custom regexes case-sensitively, as written).
"""

import copy
import importlib.util
import re
from pathlib import Path

import pytest

from app.schemas.policy_management.policy_type import _validate_custom_fields

_MIGRATIONS = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "databases"
    / "migrations"
    / "postgres"
    / "alembic"
    / "versions"
    / "ai4iplatform_core"
)


def _load(filename):
    spec = importlib.util.spec_from_file_location(filename, _MIGRATIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load("c4e6a8b0d2f4_merge_seeded_pii_definitions_into_one.py")
domain_seed = _load("b7d9f1a3c5e8_seed_domain_pii_definitions.py")
FIELDS = migration._PII_POLICY_FIELDS["custom_field"]


def _regex(entity_name):
    return next(field["regex"] for field in FIELDS if field["entity_name"] == entity_name)


def test_custom_fields_and_built_ins_are_seeded():
    assert set(migration._PII_POLICY_FIELDS) == {"custom_field", "model_supported_field"}


def test_built_ins_are_the_domain_definitions_combined():
    # Inference runs only the built-ins named here; one dropped in the merge
    # would go unmasked for every policy moved onto this row.
    domain_names = [
        entity["entity_name"]
        for definition in domain_seed._DOMAIN_PII_DEFINITIONS.values()
        for entry in definition["model_supported_field"]
        for entity in entry["en"]
    ]
    [entry] = migration._PII_POLICY_FIELDS["model_supported_field"]
    names = [entity["entity_name"] for entity in entry["en"]]
    assert names == list(dict.fromkeys(domain_names))


def test_policy_fields_pass_the_policy_type_api_validation():
    fields = copy.deepcopy(migration._PII_POLICY_FIELDS)
    # The validator cleans entity names in place; a seeded name it would
    # change is one the API would rewrite on the next edit.
    assert _validate_custom_fields(fields) == migration._PII_POLICY_FIELDS


def test_custom_fields_are_the_domain_definitions_combined():
    domain_fields = [
        field
        for definition in domain_seed._DOMAIN_PII_DEFINITIONS.values()
        for field in definition["custom_field"]
    ]
    assert FIELDS == domain_fields


def test_entity_names_are_unique():
    names = [field["entity_name"] for field in FIELDS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("field", FIELDS, ids=[field["entity_name"] for field in FIELDS])
def test_regex_matches_each_of_its_examples(field):
    for example in field["examples"]:
        assert re.fullmatch(field["regex"], example), f"{field['entity_name']}: {example!r}"


@pytest.mark.parametrize(
    "entity_name, text",
    [
        ("TRANSACTION_ID", "25000000"),
        ("TRANSACTION_ID", "SBIN0000456"),      # IFSC code
        ("HEALTH_INSURANCE_ID", "COVID19"),
        ("HEALTH_INSURANCE_ID", "560001"),      # PIN code
        ("ADDRESS", "5 students in class"),
        ("ADDRESS", "12-08-2004"),
        ("UPI_ID", "a.b@gmail.com"),
    ],
)
def test_regex_ignores_lookalikes(entity_name, text):
    assert not re.search(_regex(entity_name), text)


def test_every_earlier_seeder_id_is_replaced():
    earlier = {
        "5eed0001-0000-0000-0000-000000000001",
        "5eed0001-0000-0000-0000-000000000002",
        "5eed0001-0000-0000-0000-000000000003",
        domain_seed.SEEDER_ID,
    }
    assert set(migration.EARLIER_SEEDER_IDS) == earlier
    assert migration.SEEDER_ID not in earlier
