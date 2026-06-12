"""camelcase_adapter_input_paths

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-06-12 00:00:00.000000

Aligns adapter_config input value_paths to camelCase (ULCA), the casing the
frontend and all API callers already send. This lets the input renderer drop
its snake->camel fallback and the per-service config-normalise overrides
(AI4IDS-1981 follow-up).

Explicit per-model, like the other adapter_config migrations. Only the models
that carried snake_case request.config.* paths are touched; models already on
camelCase (transliteration, ner, ...) are left alone. Internal injected paths
(request.config.is_word_level / top_k) and context paths (input.* / audio.*)
are not request-wire keys and are unchanged.

For the optional diarization inputs the rename also adds a "" default
(value:""), so an absent config key resolves without a service-side normalise:
  numSpeakers (speaker-diarization), targetLanguage (language-diarization).

Symmetric and reversible in place: downgrade restores the snake paths and drops
the added defaults. Idempotent. Keyed by mm_models.name.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


# (model_name, [(tensor, snake_path, camel_path, default_or_None), ...])
_CHANGES = [
    ("indictrans", [
        ("INPUT_LANGUAGE_ID", "request.config.language.source_language",
         "request.config.language.sourceLanguage", None),
        ("OUTPUT_LANGUAGE_ID", "request.config.language.target_language",
         "request.config.language.targetLanguage", None),
    ]),
    ("asr-am-ensemble", [
        ("LANG_ID", "request.config.language.source_language",
         "request.config.language.sourceLanguage", None),
    ]),
    ("lang-diarization", [
        ("LANGUAGE", "request.config.target_language",
         "request.config.targetLanguage", ""),
    ]),
    ("speaker-diarization", [
        ("NUM_SPEAKERS", "request.config.num_speakers",
         "request.config.numSpeakers", ""),
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


def _update_tensor(inp: dict, snake: str, camel: str, default, forward: bool) -> bool:
    """Rename one input tensor's value_path and add/drop its default. Returns
    True if the tensor changed."""
    src, dst = (snake, camel) if forward else (camel, snake)
    changed = False
    if inp.get("value_path") == src:
        inp["value_path"] = dst
        changed = True
    if default is not None:
        if forward and inp.get("value") is None:
            inp["value"] = default
            changed = True
        elif not forward and inp.get("value") == default:
            inp.pop("value", None)
            changed = True
    return changed


def _apply(forward: bool) -> None:
    conn = op.get_bind()
    for name, tensors in _CHANGES:
        cfg = _load(conn, name)
        if cfg is None:
            print(f"  SKIP {name}: no adapter_config")
            continue
        by_name = {t[0]: t for t in tensors}
        changed = False
        for inp in cfg.get("inputs", []):
            spec = by_name.get(inp.get("tensor"))
            if spec and _update_tensor(inp, spec[1], spec[2], spec[3], forward):
                changed = True
        if changed:
            _write(conn, name, cfg)
            print(f"  OK {name}: input value_paths aligned")


def upgrade() -> None:
    _apply(forward=True)


def downgrade() -> None:
    _apply(forward=False)
