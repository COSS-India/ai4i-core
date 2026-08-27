"""seed_inference_types

Seeds the 12 rows of the `inference_types` catalogue created by 3b6faeb2bff6.

Transcribed from libs/ai4i_core/ai4i_core/ppu/inference_types.yaml, which stays
authoritative for now — nothing reads this table yet (see 2935_IMPLEMENTATION.md
§7.1). The YAML's `endpoint_pattern` plus `endpoint_aliases` are folded into the
single `endpoint_patterns` array; `llm` is the only type with more than one.

Kept separate from the DDL revision so the data load can be rolled back and
re-applied without dropping the table.

Revision ID: b41ed153cac5
Revises: 3b6faeb2bff6
Create Date: 2026-08-26 17:45:23.363456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b41ed153cac5'
down_revision: Union[str, None] = '3b6faeb2bff6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, endpoint_patterns, unit, pricing)
_INFERENCE_TYPES = (
    ('llm', ['/api/v1/chat', '/api/v1/chat/completions'], 'tokens', 'per_million_tokens'),
    ('asr', ['/api/v1/asr/inference'], 'audio_minutes', 'per_minute'),
    ('nmt', ['/api/v1/nmt/inference'], 'characters', 'per_million_characters'),
    ('tts', ['/api/v1/tts/inference'], 'characters', 'per_million_characters'),
    ('ner', ['/api/v1/ner/inference'], 'characters', 'per_million_characters'),
    ('ocr', ['/api/v1/ocr/inference'], 'images', 'per_image'),
    ('transliteration', ['/api/v1/transliteration/inference'], 'characters', 'per_million_characters'),
    ('language-detection', ['/api/v1/language-detection/inference'], 'characters', 'per_million_characters'),
    ('language-diarization', ['/api/v1/language-diarization/inference'], 'audio_minutes', 'per_minute'),
    ('speaker-diarization', ['/api/v1/speaker-diarization/inference'], 'audio_minutes', 'per_minute'),
    ('audio-lang-detection', ['/api/v1/audio-lang-detection/inference'], 'audio_minutes', 'per_minute'),
    ('pipeline', ['/api/v1/pipeline/inference'], 'requests', 'per_request'),
)


def upgrade() -> None:
    conn = op.get_bind()
    # ON CONFLICT DO NOTHING so re-running against an environment that already
    # holds some of these names is a no-op rather than a constraint violation.
    for name, patterns, unit, pricing in _INFERENCE_TYPES:
        conn.execute(
            sa.text(
                "INSERT INTO inference_types (name, endpoint_patterns, unit, pricing)"
                " VALUES (:name, CAST(:patterns AS text[]), :unit, :pricing)"
                " ON CONFLICT (name) DO NOTHING"
            ),
            {"name": name, "patterns": patterns, "unit": unit, "pricing": pricing},
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Delete only the seeded names — never a bare DELETE FROM. Once admins can
    # add inference types through the API, rolling back this seed must not take
    # their rows with it.
    conn.execute(
        sa.text("DELETE FROM inference_types WHERE name = ANY(:names)"),
        {"names": [name for name, _, _, _ in _INFERENCE_TYPES]},
    )
