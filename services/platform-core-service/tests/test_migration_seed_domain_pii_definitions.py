"""Unit tests for the domain PII definitions seed migration (b7d9f1a3c5e8).

The seeded rows bypass the policy-type API, so these check they would pass its
validation on the next edit, and that each regex matches its own examples
(inference matches custom regexes case-sensitively, as written).
"""

import copy
import importlib.util
import re
from pathlib import Path

import pytest

from app.schemas.policy_management.policy_type import _validate_custom_fields

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "databases"
    / "migrations"
    / "postgres"
    / "alembic"
    / "versions"
    / "ai4iplatform_core"
    / "b7d9f1a3c5e8_seed_domain_pii_definitions.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("seed_domain_pii_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load()
DEFINITIONS = migration._DOMAIN_PII_DEFINITIONS
CUSTOM_FIELDS = [
    (name, field) for name, fields in DEFINITIONS.items() for field in fields["custom_field"]
]


def _regex(entity_name):
    return next(field["regex"] for _, field in CUSTOM_FIELDS if field["entity_name"] == entity_name)


def _model_entities(fields):
    return {
        entity["entity_name"]
        for entry in fields.get("model_supported_field", [])
        for entities in entry.values()
        for entity in entities
    }


def test_seeds_the_three_domain_definitions():
    assert set(DEFINITIONS) == {"Education PII", "Finance PII", "Healthcare PII"}


@pytest.mark.parametrize("name", sorted(DEFINITIONS))
def test_policy_fields_pass_the_policy_type_api_validation(name):
    fields = copy.deepcopy(DEFINITIONS[name])
    # The validator cleans entity names in place; a seeded name it would
    # change is one the API would rewrite on the next edit.
    assert _validate_custom_fields(fields) == DEFINITIONS[name]


@pytest.mark.parametrize(
    "name, field", CUSTOM_FIELDS, ids=[field["entity_name"] for _, field in CUSTOM_FIELDS]
)
def test_regex_matches_each_of_its_examples(name, field):
    for example in field["examples"]:
        assert re.fullmatch(field["regex"], example), f"{name} {field['entity_name']}: {example!r}"


def test_no_custom_entity_repeats_a_built_in():
    built_in = set().union(*(_model_entities(fields) for fields in DEFINITIONS.values()))
    custom = {field["entity_name"] for _, field in CUSTOM_FIELDS}
    assert not custom & built_in


@pytest.mark.parametrize(
    "entity_name, text",
    [
        ("TRANSACTION_ID", "25000000"),
        ("TRANSACTION_ID", "20241015"),
        ("TRANSACTION_ID", "SBIN0000456"),      # IFSC code
        ("TRANSACTION_ID", "COMPLETED"),
        ("HEALTH_INSURANCE_ID", "COVID19"),
        ("HEALTH_INSURANCE_ID", "20241015"),
        ("HEALTH_INSURANCE_ID", "560001"),      # PIN code
        ("ADDRESS", "5 students in class"),
        ("ADDRESS", "Chapter 3 Road Safety Rules"),
        ("ADDRESS", "12-08-2004"),
    ],
)
def test_regex_ignores_lookalikes(entity_name, text):
    assert not re.search(_regex(entity_name), text)


def test_downgrade_keeps_definitions_a_policy_references(monkeypatch):
    executed = []

    class Bind:
        def execute(self, statement, params=None):
            executed.append(str(statement))

    monkeypatch.setattr(migration.op, "get_bind", lambda: Bind(), raising=False)
    migration.downgrade()

    (sql,) = executed
    assert "created_by = :seeder_id" in sql
    assert "NOT EXISTS" in sql and "ANY(p.policy_type_id)" in sql
