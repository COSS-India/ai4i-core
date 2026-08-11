"""fix_llm_target_language

The original seeder (d3e850228f7e) seeded the "llm" model's languages as
source-only entries and left request_schema.config empty, unlike nmt/
transliteration which pair source+target. The adapter-config seeder
(a1f2e3d4c5b6) also never added an "llm" entry to ADAPTER_CONFIGS, so the
model's inference_endpoint never got a target-language mapping. The same
seeder also left the "llm-indic-prod" service unpublished by default. This
migration patches the already-seeded "llm" row and its service in place
(fresh envs still get the old seeders unchanged, but this backfills any DB
that already ran them).

Also re-applies server_default='false' on mm_services.is_try_it_default:
f4a6c8e0b2d4 dropped it under the assumption the ORM model only declared a
Python-side default, but the ORM model (app/models/service.py) does declare
server_default="false" — dropping it there was itself the bug, and this
migration corrects it back to match the model.

Revision ID: f2a4c6e8b0d2
Revises: 021f3168f9c8
Create Date: 2026-08-06 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2a4c6e8b0d2'
down_revision: Union[str, None] = '021f3168f9c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

LLM_LANG_INFO = [
    ("hi", "Hindi", "Deva"),
    ("en", "English", "Latn"),
    ("ta", "Tamil", "Taml"),
    ("te", "Telugu", "Telu"),
    ("bn", "Bengali", "Beng"),
    ("mr", "Marathi", "Deva"),
    ("gu", "Gujarati", "Gujr"),
    ("kn", "Kannada", "Knda"),
    ("ml", "Malayalam", "Mlym"),
    ("pa", "Punjabi", "Guru"),
    ("or", "Odia", "Orya"),
]

# Any-to-any: every supported language can target every other supported
# language (the LLM is a general multilingual chat model, not restricted to
# same-language responses), including the same-language case.
LLM_LANGUAGES = [
    {
        "sourceLanguage": src_code, "sourceLanguageName": src_name, "sourceScriptCode": src_script,
        "targetLanguage": tgt_code, "targetLanguageName": tgt_name, "targetScriptCode": tgt_script,
    }
    for src_code, src_name, src_script in LLM_LANG_INFO
    for tgt_code, tgt_name, tgt_script in LLM_LANG_INFO
]

# Previous source-only shape, kept so downgrade() can restore it exactly.
LLM_LANGUAGES_OLD = [{"sourceLanguage": code} for code, _, _ in LLM_LANG_INFO]

LLM_ADAPTER_CONFIG = {
    "model_name": "google/gemma-4-31B-it",
    "inputs": [
        {"dtype": "BYTES", "shape": [1, 1], "tensor": "INPUT_TEXT", "value_path": "input.source"},
        {"dtype": "BYTES", "shape": [1, 1], "tensor": "INPUT_LANGUAGE_ID", "value_path": "request.config.language.source_language"},
        {"dtype": "BYTES", "shape": [1, 1], "tensor": "OUTPUT_LANGUAGE_ID", "value_path": "request.config.language.target_language"},
    ],
    "outputs": [{"dtype": "BYTES", "tensor": "OUTPUT_TEXT", "maps_to": "target"}],
    "version": "1.0", "model_version": "1",
}


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text("""
            UPDATE mm_models
            SET languages = CAST(:languages AS jsonb),
                inference_endpoint = jsonb_set(
                    jsonb_set(
                        inference_endpoint,
                        '{schema,request,config,language}',
                        CAST(:request_language AS jsonb),
                        true
                    ),
                    '{adapterConfig}',
                    CAST(:adapter_config AS jsonb),
                    true
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE name = 'llm' AND version = '1.0.0' AND inference_endpoint IS NOT NULL
        """),
        {
            "languages": json.dumps(LLM_LANGUAGES),
            "request_language": json.dumps({"sourceLanguage": "hi", "targetLanguage": "hi"}),
            "adapter_config": json.dumps(LLM_ADAPTER_CONFIG),
        },
    )

    # Preserve the "at most one default per task_type" invariant that
    # ServiceRepository.clear_try_it_default enforces on the API path — raw
    # SQL bypasses it, so clear any other llm service's flag first.
    conn.execute(
        sa.text("""
            UPDATE mm_services
            SET is_try_it_default = false
            WHERE task_type = 'llm' AND name <> 'llm-indic-prod'
        """),
    )

    conn.execute(
        sa.text("""
            UPDATE mm_services
            SET is_published = true,
                is_try_it_default = true,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = 'llm-indic-prod'
        """),
    )

    op.alter_column('mm_services', 'is_try_it_default',
               existing_type=sa.BOOLEAN(),
               server_default='false',
               existing_nullable=False)


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text("""
            UPDATE mm_models
            SET languages = CAST(:languages AS jsonb),
                inference_endpoint = (inference_endpoint - 'adapterConfig')
                    #- '{schema,request,config,language}',
                updated_at = CURRENT_TIMESTAMP
            WHERE name = 'llm' AND version = '1.0.0' AND inference_endpoint IS NOT NULL
        """),
        {"languages": json.dumps(LLM_LANGUAGES_OLD)},
    )

    conn.execute(
        sa.text("""
            UPDATE mm_services
            SET is_published = false,
                is_try_it_default = false,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = 'llm-indic-prod'
        """),
    )

    op.alter_column('mm_services', 'is_try_it_default',
               existing_type=sa.BOOLEAN(),
               server_default=None,
               existing_nullable=False)
