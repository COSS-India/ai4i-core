"""transliteration_topk_from_numsuggestions

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-06-12 00:00:00.000000

top_k is a plain rename of the request's numSuggestions, so the TOP_K input
reads request.config.numSuggestions directly (default 0) instead of an
is-word-level-style derived field. This drops the service-side top_k injection
(AI4IDS-1981 follow-up). is_word_level stays a code derivation (not isSentence),
which the typed input path cannot express.

Reversible in place. Idempotent. Keyed by mm_models.name 'transliteration'.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


_MODEL_NAME = "transliteration"
_TENSOR = "TOP_K"
_OLD_PATH = "request.config.top_k"
_NEW_PATH = "request.config.numSuggestions"


def _load(conn):
    row = conn.execute(
        sa.text(
            "SELECT inference_endpoint->'adapter_config' FROM mm_models WHERE name = :name"
        ),
        {"name": _MODEL_NAME},
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def _write(conn, cfg):
    conn.execute(
        sa.text(
            "UPDATE mm_models SET inference_endpoint = jsonb_set("
            "inference_endpoint, '{adapter_config}', CAST(:cfg AS jsonb)) WHERE name = :name"
        ),
        {"cfg": json.dumps(cfg), "name": _MODEL_NAME},
    )


def _apply(forward: bool) -> None:
    conn = op.get_bind()
    cfg = _load(conn)
    if cfg is None:
        print(f"  SKIP {_MODEL_NAME}: no adapter_config")
        return
    src, dst = (_OLD_PATH, _NEW_PATH) if forward else (_NEW_PATH, _OLD_PATH)
    changed = False
    for inp in cfg.get("inputs", []):
        if inp.get("tensor") != _TENSOR or inp.get("value_path") != src:
            continue
        inp["value_path"] = dst
        if forward and inp.get("value") is None:
            inp["value"] = 0          # numSuggestions optional -> default 0
            changed = True
        elif not forward and inp.get("value") == 0:
            inp.pop("value", None)
        changed = True
    if changed:
        _write(conn, cfg)
        print(f"  OK {_MODEL_NAME}: TOP_K input re-pointed")


def upgrade() -> None:
    _apply(forward=True)


def downgrade() -> None:
    _apply(forward=False)
