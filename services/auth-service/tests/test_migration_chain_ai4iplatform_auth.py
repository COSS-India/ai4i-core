"""The ai4iplatform_auth migration chain must stay linear.

Two revisions sharing a down_revision give two heads, and `alembic upgrade
head` then fails with "Multiple head revisions" — e.g. a7c3e9f15b28 and
b8a1957cd6a3 both hanging off e7a1b2c3d4f5 after a release-branch merge.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("alembic")
from alembic.config import Config
from alembic.script import ScriptDirectory

_ALEMBIC_DIR = Path(__file__).resolve().parents[3] / "infrastructure" / "databases" / "migrations" / "postgres" / "alembic"


@pytest.fixture(scope="module")
def script():
    sys.path.insert(0, str(_ALEMBIC_DIR))  # some revisions import migration_registry
    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("version_path_separator", "os")  # the checkout path may contain spaces
    cfg.set_main_option("version_locations", str(_ALEMBIC_DIR / "versions" / "ai4iplatform_auth"))
    return ScriptDirectory.from_config(cfg)


def test_single_head(script):
    assert len(script.get_heads()) == 1, f"multiple heads: {script.get_heads()}"


def test_role_reset_runs_after_creation_type_backfill(script):
    # a7c3e9f15b28 only resets users e7a1b2c3d4f5 left as self-registered.
    ancestors = {rev.revision for rev in script.iterate_revisions("a7c3e9f15b28", "base")}
    assert "e7a1b2c3d4f5" in ancestors


def test_role_reset_runs_after_usage_viewer_rename(script):
    # a7c3e9f15b28 preserves 'USAGE VIEWER' by name; on a DB still holding
    # 'PROGRAM ADMIN' those users would be reset instead.
    ancestors = {rev.revision for rev in script.iterate_revisions("a7c3e9f15b28", "base")}
    assert "c5d6e7f8a9b1" in ancestors
