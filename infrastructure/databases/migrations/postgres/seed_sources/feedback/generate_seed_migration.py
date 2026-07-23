"""
Regenerates the `ROWS` list used by the ef_feedback_reason seed migration
(infrastructure/databases/migrations/postgres/alembic/versions/
ai4iplatform_core/387af777b0fb_seed_ef_feedback_reason_data.py) from
feedback_reasons_source.json in this directory.

Source of truth is the JSON file, not the migration: to add a reason, add a
new task type (e.g. one of the 7 still missing a seeded catalog: ocr, ner,
transliteration, language-detection, audio-lang-detection,
speaker-diarization, language-diarization), or fix a translation, edit
feedback_reasons_source.json and rerun this script -- never hand-edit ROWS
in the migration file directly, or the two will drift.

Usage:
    python infrastructure/databases/migrations/postgres/seed_sources/feedback/generate_seed_migration.py
        Prints the `ROWS = [...]` assignment to stdout. Paste it into a
        migration generated via
        `python infrastructure/databases/cli.py make:migration <name> \
            --postgres-db ai4iplatform_core`
        (fill in the revision/down_revision the CLI assigns, and the
        upgrade()/downgrade() bodies -- copy them from 387af777b0fb, they
        are generic over ROWS).

    python infrastructure/databases/migrations/postgres/seed_sources/feedback/generate_seed_migration.py --check
        Regenerates ROWS and diffs it against the ROWS currently committed
        in 387af777b0fb_seed_ef_feedback_reason_data.py, to catch source/
        migration drift in CI or before a PR. Exits non-zero on a mismatch.

Every task type gets an automatic trailing "other" catch-all reason, so the
per-task-type reason list in the JSON should not include one.
"""

import json
import pprint
import re
import sys
from pathlib import Path

SOURCE_PATH = Path(__file__).parent / "feedback_reasons_source.json"

SEEDED_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic/versions/ai4iplatform_core"
    / "387af777b0fb_seed_ef_feedback_reason_data.py"
)

OTHER_LABEL = "Other"
OTHER_LABEL_I18N = {
    "as": "Other", "bn": "Other", "brx": "Other", "doi": "Other", "en": "Other",
    "gu": "Other", "hi": "Other", "kn": "Other", "ks": "Other", "mai": "Other",
    "ml": "Other", "mni": "Other", "mr": "Other", "ne": "Other", "or": "Other",
    "pa": "Other", "sa": "Other", "ta": "Other", "te": "Other", "ur": "Other",
}


def build_rows(source: dict) -> list[dict]:
    rows = []
    for task_type in source["task_order"]:
        task = source["tasks"][task_type]
        reasons = task["reasons"]
        for idx, reason in enumerate(reasons):
            rows.append(
                dict(
                    task_type=task_type,
                    code=reason["code"],
                    label=reason["label"],
                    label_i18n=reason["label_i18n"],
                    description=task["description"],
                    sort_order=idx,
                    is_active=True,
                )
            )
        rows.append(
            dict(
                task_type=task_type,
                code="other",
                label=OTHER_LABEL,
                label_i18n=OTHER_LABEL_I18N,
                description=None,
                sort_order=len(reasons),
                is_active=True,
            )
        )
    return rows


def render_rows(rows: list[dict]) -> str:
    return "ROWS = " + pprint.pformat(rows, indent=4, sort_dicts=False)


def _committed_rows_text() -> str:
    src = SEEDED_MIGRATION_PATH.read_text(encoding="utf-8")
    match = re.search(r"^ROWS = \[", src, re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not find a ROWS assignment in {SEEDED_MIGRATION_PATH}")
    start = match.start()
    open_idx = src.index("[", start)
    depth = 0
    for i in range(open_idx, len(src)):
        if src[i] == "[":
            depth += 1
        elif src[i] == "]":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise SystemExit("Unbalanced brackets while scanning ROWS in the committed migration")


def main() -> None:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    rendered = render_rows(build_rows(source))

    if "--check" in sys.argv:
        committed = _committed_rows_text()
        if rendered != committed:
            sys.stderr.write(
                "feedback_reasons_source.json has drifted from the committed "
                f"ROWS in {SEEDED_MIGRATION_PATH.name}.\n"
                "Regenerate (this script without --check) and author a new "
                "migration with the updated ROWS -- do not edit an already-"
                "applied migration in place.\n"
            )
            sys.exit(1)
        print("OK: source matches the committed seed migration.")
        return

    sys.stdout.buffer.write(rendered.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
