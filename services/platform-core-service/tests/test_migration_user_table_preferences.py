"""Migration b8d2f4a6c0e1 (user_table_preferences): revision chain, and the DDL
upgrade()/downgrade() emit (rendered offline, no database needed)."""
import importlib.util
import io
import re
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


def _all_revisions():
    revs, downs = {}, set()
    for f in _VERSIONS.glob("*.py"):
        text = f.read_text()
        r = re.search(r"^revision(?:: str)?\s*=\s*['\"](\w+)", text, re.M)
        d = re.search(r"^down_revision.*?=\s*(.+)$", text, re.M)
        if r:
            revs[r.group(1)] = f.name
            downs.update(re.findall(r"['\"](\w{6,})['\"]", d.group(1)))
    return revs, downs


def test_revision_ids():
    m = _load()
    assert m.revision == "b8d2f4a6c0e1"
    assert m.down_revision == "e2f4a6c8b0d3"


def test_down_revision_exists_and_this_is_the_head():
    revs, downs = _all_revisions()
    assert "e2f4a6c8b0d3" in revs
    assert [r for r in revs if r not in downs] == ["b8d2f4a6c0e1"]


def test_upgrade_creates_table_with_unique_constraint():
    sql = _sql(_load().upgrade)
    assert "CREATE TABLE user_table_preferences" in sql
    assert "visible_columns JSONB NOT NULL" in sql
    assert "CONSTRAINT uq_user_table_preferences_user_view UNIQUE (user_id, view_key)" in sql


def test_downgrade_drops_table():
    assert "DROP TABLE user_table_preferences" in _sql(_load().downgrade)
