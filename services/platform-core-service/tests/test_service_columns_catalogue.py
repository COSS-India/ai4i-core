"""Service List column catalogue invariants."""

from app.schemas.model_management.service_columns import (
    ADMIN_ONLY_FILTER_PARAMS,
    MANDATORY_KEYS,
    SERVICE_LIST_COLUMNS,
    SORTABLE_KEYS,
)


def test_ids_are_unique():
    ids = [c.id for c in SERVICE_LIST_COLUMNS]
    assert len(ids) == len(set(ids)) == 13


def test_mandatory_columns_are_name_and_actions():
    assert MANDATORY_KEYS == {"name", "actions"}


def test_actions_is_not_sortable():
    assert "actions" not in SORTABLE_KEYS
    # availability is also non-sortable: it's computed live, nothing stored to ORDER BY on.
    assert SORTABLE_KEYS == {c.id for c in SERVICE_LIST_COLUMNS} - {"actions", "availability"}


def test_filterable_columns_declare_params():
    for col in SERVICE_LIST_COLUMNS:
        assert bool(col.filter_params) == col.filterable, col.id


def test_admin_only_filter_params():
    # tier_ids belongs to an admin-only column but is open to every caller
    # (FILTER_PARAMS_OPEN_TO_ALL): the Application fallback picker uses it.
    assert ADMIN_ONLY_FILTER_PARAMS == {
        "created_from", "created_to", "published_from", "published_to",
    }
