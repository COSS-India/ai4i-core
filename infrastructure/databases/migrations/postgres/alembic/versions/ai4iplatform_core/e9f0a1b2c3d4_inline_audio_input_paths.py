"""inline_audio_input_paths

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-06-12 00:00:00.000000

Points audio input value_paths at the input item directly (input.*) instead of
the old audio.* context namespace. The per-service _triton_context_builder hook
only copied item fields into that namespace; reading the item directly removes
the hook (AI4IDS-1981 follow-up). Preprocessing writes the fields onto the item
(audioContent passthrough; ASR's samples/num_samples), so they are reachable as
input.<field>.

Explicit per-model, like the other adapter_config migrations. Symmetric and
reversible. Idempotent. Keyed by mm_models.name.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


# (model_name, [(tensor, old_path, new_path), ...])
_CHANGES = [
    ("asr-am-ensemble", [
        ("AUDIO_SIGNAL", "audio.samples", "input.samples"),
        ("NUM_SAMPLES", "audio.num_samples", "input.num_samples"),
    ]),
    ("ald", [
        ("AUDIO_DATA", "audio.audio_content", "input.audioContent"),
    ]),
    ("lang-diarization", [
        ("AUDIO_DATA", "audio.audio_content", "input.audioContent"),
    ]),
    ("speaker-diarization", [
        ("AUDIO_DATA", "audio.audio_content", "input.audioContent"),
    ]),
]


def _load(conn, name):
    row = conn.execute(
        sa.text(
            "SELECT inference_endpoint->'adapter_config' FROM mm_models WHERE name = :name"
        ),
        {"name": name},
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def _write(conn, name, cfg):
    conn.execute(
        sa.text(
            "UPDATE mm_models SET inference_endpoint = jsonb_set("
            "inference_endpoint, '{adapter_config}', CAST(:cfg AS jsonb)) WHERE name = :name"
        ),
        {"cfg": json.dumps(cfg), "name": name},
    )


def _apply(forward: bool) -> None:
    conn = op.get_bind()
    for name, tensors in _CHANGES:
        cfg = _load(conn, name)
        if cfg is None:
            print(f"  SKIP {name}: no adapter_config")
            continue
        moves = {t[0]: (t[1], t[2]) if forward else (t[2], t[1]) for t in tensors}
        changed = False
        for inp in cfg.get("inputs", []):
            move = moves.get(inp.get("tensor"))
            if move and inp.get("value_path") == move[0]:
                inp["value_path"] = move[1]
                changed = True
        if changed:
            _write(conn, name, cfg)
            print(f"  OK {name}: audio input value_paths re-pointed")


def upgrade() -> None:
    _apply(forward=True)


def downgrade() -> None:
    _apply(forward=False)
