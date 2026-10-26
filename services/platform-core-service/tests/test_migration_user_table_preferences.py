"""Migration b8d2f4a6c0e1 (user_table_preferences): revision ids, and the DDL
upgrade()/downgrade() emit (rendered offline, no database needed). Head and
chain integrity are checked by scripts/validate-migrations.py."""
import importlib.util
import io
import sys
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_VERSIONS = (
    Path(__file__).resolve().parents[3]
    / "infrastructure" / "databases" / "migrations" / "postgres" / "alembic"
    / "versions" / "ai4iplatform_core"
)
_FILE = "b8d2f4a6c0e1_add_user_table_preferences.py"


def _load():
    path = _VERSIONS / _FILE
    spec = importlib.util.spec_from_file_location("_migration_user_table_prefs", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sql(step) -> str:
    buf = io.StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buf}
    )
    with Operations.context(ctx):
        step()
    return buf.getvalue()


def test_revision_ids():
    m = _load()
    assert m.revision == "b8d2f4a6c0e1"
    assert m.down_revision == "b7d9f1a3c5e8"


def test_upgrade_creates_table_with_unique_constraint():
    sql = _sql(_load().upgrade)
    assert "CREATE TABLE user_table_preferences" in sql
    assert "visible_columns JSONB NOT NULL" in sql
    assert "CONSTRAINT uq_user_table_preferences_user_view UNIQUE (user_id, view_key)" in sql


def test_downgrade_drops_table():
    assert "DROP TABLE user_table_preferences" in _sql(_load().downgrade)
