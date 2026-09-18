"""seed_inference_types

Seeds the 12 inference types currently defined in
``libs/ai4i_core/ai4i_core/ppu/inference_types.yaml``.

``endpoint_patterns[0]`` is the canonical path; further elements are the YAML's
``endpoint_aliases``. Only ``llm`` has one today.

Kept separate from the DDL revision so the data can be rolled back and
re-applied without touching the table. ``ON CONFLICT DO NOTHING`` makes
re-running ``migrate.sh all upgrade`` — this repo's seed mechanism — a no-op.

Revision ID: 52eb3034332e
Revises: 80d597c64a58
Create Date: 2026-08-31 15:47:12.114553

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '52eb3034332e'
down_revision: Union[str, None] = '80d597c64a58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TYPES = [
    ("llm", ["/api/v1/chat", "/api/v1/chat/completions"], "tokens", "per_million_tokens"),
    ("asr", ["/api/v1/asr/inference"], "audio_minutes", "per_minute"),
    ("nmt", ["/api/v1/nmt/inference"], "characters", "per_million_characters"),
    ("tts", ["/api/v1/tts/inference"], "characters", "per_million_characters"),
    ("ner", ["/api/v1/ner/inference"], "characters", "per_million_characters"),
    ("ocr", ["/api/v1/ocr/inference"], "images", "per_image"),
    ("transliteration", ["/api/v1/transliteration/inference"], "characters", "per_million_characters"),
    ("language-detection", ["/api/v1/language-detection/inference"], "characters", "per_million_characters"),
    ("language-diarization", ["/api/v1/language-diarization/inference"], "audio_minutes", "per_minute"),
    ("speaker-diarization", ["/api/v1/speaker-diarization/inference"], "audio_minutes", "per_minute"),
    ("audio-lang-detection", ["/api/v1/audio-lang-detection/inference"], "audio_minutes", "per_minute"),
    ("pipeline", ["/api/v1/pipeline/inference"], "requests", "per_request"),
]


def _pg_text_array(values: list[str]) -> str:
    """Render a Python list as a Postgres text[] literal, escaping quotes."""
    escaped = ",".join('"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"' for v in values)
    return "{" + escaped + "}"


def upgrade() -> None:
    rows = ",\n    ".join(
        "('{name}', '{patterns}'::text[], '{unit}', '{pricing}')".format(
            name=name, patterns=_pg_text_array(patterns), unit=unit, pricing=pricing
        )
        for name, patterns, unit, pricing in _TYPES
    )
    op.execute(
        "INSERT INTO inference_types (name, endpoint_patterns, unit, pricing) VALUES\n"
        f"    {rows}\n"
        "ON CONFLICT (name) DO NOTHING;"
    )


def downgrade() -> None:
    names = ",".join(f"'{name}'" for name, _, _, _ in _TYPES)
    # Targeted delete, never TRUNCATE — an operator may have added types via
    # the CRUD API and those are not this revision's to remove.
    op.execute(f"DELETE FROM inference_types WHERE name IN ({names});")
