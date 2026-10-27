"""Service List column catalogue invariants."""

from app.schemas.model_management.service_columns import (
    ADMIN_ONLY_FILTER_PARAMS,
    ADMIN_ONLY_KEYS,
    DEFAULT_VISIBLE_KEYS,
    MANDATORY_KEYS,
    SERVICE_LIST_COLUMNS,
    SORTABLE_KEYS,
    columns_for_caller,
)


def test_ids_are_unique():
    ids = [c.id for c in SERVICE_LIST_COLUMNS]
    assert len(ids) == len(set(ids)) == 12


def test_mandatory_columns_are_name_and_actions():
    assert MANDATORY_KEYS == {"name", "actions"}


def test_mandatory_columns_are_default_visible():
    assert MANDATORY_KEYS <= DEFAULT_VISIBLE_KEYS


def test_default_set():
    assert DEFAULT_VISIBLE_KEYS == {"name", "actions", "task_type", "tier", "status", "created_at"}


def test_actions_is_not_sortable():
    assert "actions" not in SORTABLE_KEYS
    assert SORTABLE_KEYS == {c.id for c in SERVICE_LIST_COLUMNS} - {"actions"}


def test_filterable_columns_declare_params():
    for col in SERVICE_LIST_COLUMNS:
        assert bool(col.filter_params) == col.filterable, col.id


def test_admin_sees_every_column_in_order():
    assert columns_for_caller(True) == SERVICE_LIST_COLUMNS


def test_non_admin_never_sees_admin_only_columns():
    visible = {c.id for c in columns_for_caller(False)}
    assert visible.isdisjoint(ADMIN_ONLY_KEYS)
    assert visible == {"name", "actions", "task_type", "status", "model_name", "service_id"}


def test_non_admin_keeps_a_non_mandatory_default():
    visible_defaults = {c.id for c in columns_for_caller(False) if c.default_visible}
    assert visible_defaults - MANDATORY_KEYS


def test_admin_only_filter_params():
    # tier_ids stays filterable by everyone (Application fallback picker,
    # AI4IDS-3488) although the tier column itself is admin-only.
    assert ADMIN_ONLY_FILTER_PARAMS == {
        "created_from", "created_to", "published_from", "published_to",
    }
