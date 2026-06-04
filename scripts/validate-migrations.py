#!/usr/bin/env python3
"""
Validate migration integrity without requiring a running database.
Run this in CI on every PR to catch migration issues before they reach production.

Checks performed:
  1. All model files referenced by migration_registry.py exist
  2. Alembic revision chains are intact (no broken down_revision references)
  3. No stale __pycache__ entries for deleted migrations

Usage:
  python scripts/validate-migrations.py

Exit codes:
  0 = all checks pass
  1 = one or more checks failed

Compatible with: macOS, Ubuntu, Windows
"""

import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
REGISTRY = (
    PROJECT_ROOT
    / "infrastructure"
    / "databases"
    / "migrations"
    / "postgres"
    / "alembic"
    / "migration_registry.py"
)
VERSIONS_DIR = (
    PROJECT_ROOT
    / "infrastructure"
    / "databases"
    / "migrations"
    / "postgres"
    / "alembic"
    / "versions"
)

# Support colored output on all platforms
USE_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
if sys.platform == "win32":
    # Enable ANSI colors on Windows 10+
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        USE_COLOR = False


def _c(code, text):
    if USE_COLOR:
        return f"\033[{code}m{text}\033[0m"
    return text


errors = 0
warnings = 0


def fail(msg):
    global errors
    print(f"  {_c('0;31', 'FAIL')}  {msg}")
    errors += 1


def ok(msg):
    print(f"  {_c('0;32', 'PASS')}  {msg}")


def warn(msg):
    global warnings
    print(f"  {_c('0;33', 'WARN')}  {msg}")
    warnings += 1


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1: All model files referenced in migration_registry.py exist
# ─────────────────────────────────────────────────────────────────────────────
def check_model_files():
    print("\n=== Check 1: Model file references ===")

    if not REGISTRY.exists():
        fail(f"migration_registry.py not found at {REGISTRY}")
        return

    text = REGISTRY.read_text(encoding="utf-8")

    # Match  PROJECT_ROOT / "segment" / "segment" / ... patterns
    pattern = r'PROJECT_ROOT\s*/\s*((?:"[^"]+"\s*/?\s*)+)'
    paths = set()
    for m in re.finditer(pattern, text):
        parts = re.findall(r'"([^"]+)"', m.group(1))
        joined = "/".join(parts)
        # Only check actual .py files, skip placeholders like <service-name>
        if joined.endswith(".py") and "<" not in joined:
            paths.add(joined)

    if not paths:
        warn("Could not extract model paths from registry")
        return

    for rel_path in sorted(paths):
        full_path = PROJECT_ROOT / rel_path.replace("/", os.sep)
        if full_path.is_file():
            ok(rel_path)
        else:
            fail(f"{rel_path} does not exist")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2: Revision chain integrity per database
# ─────────────────────────────────────────────────────────────────────────────
def check_revision_chains():
    print("\n=== Check 2: Revision chain integrity ===")

    if not VERSIONS_DIR.is_dir():
        fail(f"Versions directory not found at {VERSIONS_DIR}")
        return

    for db_dir in sorted(VERSIONS_DIR.iterdir()):
        if not db_dir.is_dir() or db_dir.name == "__pycache__":
            continue

        db_name = db_dir.name
        migration_files = sorted(
            f for f in db_dir.glob("*.py") if f.name != "__init__.py"
        )

        if not migration_files:
            ok(f"{db_name}: no migration files")
            continue

        revisions = {}  # rev_id -> filename
        down_refs = {}  # rev_id -> down_revision (None = base)

        for f in migration_files:
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                warn(f"{db_name}/{f.name}: could not read file")
                continue

            rev_match = re.search(
                r"^revision\b.*?['\"]([a-f0-9A-Z_]+)['\"]", text, re.MULTILINE
            )
            # down_revision may be a single id or a list (merge revisions:
            # down_revision = ['abc', 'def']) — capture ALL quoted ids on the line.
            down_match = re.search(
                r"^down_revision\b[^=]*=\s*(.+)$", text, re.MULTILINE
            )

            if not rev_match:
                continue

            rev = rev_match.group(1)
            downs = (
                re.findall(r"['\"]([a-f0-9A-Z_]+)['\"]", down_match.group(1))
                if down_match
                else []
            )

            if rev in revisions:
                fail(
                    f"{db_name}: duplicate revision '{rev}' "
                    f"in {f.name} and {revisions[rev]}"
                )
                continue

            revisions[rev] = f.name
            down_refs[rev] = downs

        # Verify every down_revision points to an existing revision
        chain_ok = True
        for rev, downs in down_refs.items():
            for down in downs:
                if down not in revisions:
                    fail(
                        f"{db_name}: revision '{rev}' ({revisions[rev]}) "
                        f"references down_revision '{down}' which has no migration file"
                    )
                    chain_ok = False

        # Count heads (revisions not referenced as any down_revision)
        referenced = {down for downs in down_refs.values() for down in downs}
        heads = [r for r in revisions if r not in referenced]

        if len(heads) > 1:
            fail(f"{db_name}: multiple heads detected ({len(heads)}): {heads}")
        elif chain_ok:
            ok(f"{db_name}: chain intact ({len(revisions)} revisions)")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3: No stale __pycache__ entries for deleted migrations
# ─────────────────────────────────────────────────────────────────────────────
def check_stale_pycache():
    print("\n=== Check 3: Stale __pycache__ ===")

    if not VERSIONS_DIR.is_dir():
        return

    stale_found = False
    for db_dir in sorted(VERSIONS_DIR.iterdir()):
        if not db_dir.is_dir() or db_dir.name == "__pycache__":
            continue

        cache_dir = db_dir / "__pycache__"
        if not cache_dir.is_dir():
            continue

        for pyc_file in sorted(cache_dir.glob("*.pyc")):
            # Reconstruct source .py name from  name.cpython-3XX.pyc
            stem = pyc_file.stem  # e.g. "abc123_auto.cpython-310"
            py_name = re.sub(r"\.cpython-\d+", "", stem) + ".py"
            if py_name == "__init__.py":
                continue

            src_file = db_dir / py_name
            if not src_file.exists():
                fail(
                    f"{db_dir.name}: stale cache for deleted migration "
                    f"{pyc_file.name}"
                )
                stale_found = True

    if not stale_found:
        ok("No stale __pycache__ entries found")


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 4: ON CONFLICT targets must be backed by a unique constraint
#   Catches the #837 class: `ON CONFLICT (role_id, permission_id)` on a table
#   with no matching unique constraint -> Postgres InvalidColumnReference at
#   runtime -> `upgrade head` rolls back. The revision graph looks fine, so the
#   other checks miss it; this scans the SQL statically.
#   Scoped to multi-column targets (the risky, rarely-backed case); single-column
#   conflicts are almost always backed by a column unique and would be noisy.
# ─────────────────────────────────────────────────────────────────────────────
def _trailing_idents(group: str) -> frozenset:
    # "'role_id', 'permission_id'" -> {role_id, permission_id}
    # "lower(organisation), id" -> {organisation, id}  (last identifier per item)
    # Skip keyword args like name='uq_...' so they don't pollute the column set.
    cols = set()
    for part in group.split(","):
        if "=" in part:  # kwarg (e.g. name='uq_pattern_entity_lang'), not a column
            continue
        idents = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", part)
        if idents:
            cols.add(idents[-1].lower())
    return frozenset(cols)


def check_on_conflict_targets():
    print("\n=== Check 4: ON CONFLICT targets backed by a unique constraint ===")

    if not VERSIONS_DIR.is_dir():
        return

    UNIQUE_PATTERNS = (
        r"UniqueConstraint\(([^)]+)\)",
        r"PrimaryKeyConstraint\(([^)]+)\)",
        r"create_index\([^\[]*\[([^\]]+)\][^)]*unique\s*=\s*True",
        r"CREATE UNIQUE INDEX[^(]*\(([^)]+)\)",
        r"ADD CONSTRAINT[^(]*UNIQUE\s*\(([^)]+)\)",
    )

    found_issue = False
    for db_dir in sorted(VERSIONS_DIR.iterdir()):
        if not db_dir.is_dir() or db_dir.name == "__pycache__":
            continue
        files = [f for f in db_dir.glob("*.py") if f.name != "__init__.py"]
        texts = {f: f.read_text(encoding="utf-8", errors="ignore") for f in files}

        # All multi-column unique column-sets declared anywhere in this db's chain.
        unique_sets = set()
        for text in texts.values():
            for pat in UNIQUE_PATTERNS:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    cols = _trailing_idents(m.group(1))
                    if len(cols) >= 2:
                        unique_sets.add(cols)

        for f, text in texts.items():
            for m in re.finditer(r"ON CONFLICT\s*\(([^)]+)\)", text, re.IGNORECASE):
                target = _trailing_idents(m.group(1))
                if len(target) >= 2 and target not in unique_sets:
                    fail(
                        f"{db_dir.name}/{f.name}: ON CONFLICT ({', '.join(sorted(target))}) "
                        f"has no matching multi-column unique constraint — will raise "
                        f"InvalidColumnReference at runtime. Use INSERT ... WHERE NOT EXISTS."
                    )
                    found_issue = True

    if not found_issue:
        ok("No unbacked multi-column ON CONFLICT targets")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    check_model_files()
    check_revision_chains()
    check_stale_pycache()
    check_on_conflict_targets()

    print()
    print("-" * 40)
    if errors > 0:
        print(f"{_c('0;31', 'FAILED')}: {errors} error(s), {warnings} warning(s)")
        print()
        print("Common fixes:")
        print("  - Missing model file    -> Update path in migration_registry.py")
        print("  - Broken down_revision  -> Never delete applied migration files")
        print("  - Multiple heads        -> alembic -x db=<name> merge heads -m 'merge'")
        print("  - Stale __pycache__     -> Delete the __pycache__ directory")
        print("  - Unbacked ON CONFLICT  -> Use INSERT ... WHERE NOT EXISTS (no unique constraint needed)")
        return 1
    else:
        print(f"{_c('0;32', 'ALL CHECKS PASSED')} ({warnings} warning(s))")
        return 0


if __name__ == "__main__":
    sys.exit(main())
