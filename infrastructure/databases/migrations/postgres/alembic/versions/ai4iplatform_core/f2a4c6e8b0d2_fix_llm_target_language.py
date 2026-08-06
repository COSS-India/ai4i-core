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

LLM_LANGUAGES = [
    {"sourceLanguage": "hi", "sourceLanguageName": "Hindi", "sourceScriptCode": "Deva", "targetLanguage": "hi", "targetLanguageName": "Hindi", "targetScriptCode": "Deva"},
    {"sourceLanguage": "en", "sourceLanguageName": "English", "sourceScriptCode": "Latn", "targetLanguage": "en", "targetLanguageName": "English", "targetScriptCode": "Latn"},
    {"sourceLanguage": "ta", "sourceLanguageName": "Tamil", "sourceScriptCode": "Taml", "targetLanguage": "ta", "targetLanguageName": "Tamil", "targetScriptCode": "Taml"},
    {"sourceLanguage": "te", "sourceLanguageName": "Telugu", "sourceScriptCode": "Telu", "targetLanguage": "te", "targetLanguageName": "Telugu", "targetScriptCode": "Telu"},
    {"sourceLanguage": "bn", "sourceLanguageName": "Bengali", "sourceScriptCode": "Beng", "targetLanguage": "bn", "targetLanguageName": "Bengali", "targetScriptCode": "Beng"},
    {"sourceLanguage": "mr", "sourceLanguageName": "Marathi", "sourceScriptCode": "Deva", "targetLanguage": "mr", "targetLanguageName": "Marathi", "targetScriptCode": "Deva"},
    {"sourceLanguage": "gu", "sourceLanguageName": "Gujarati", "sourceScriptCode": "Gujr", "targetLanguage": "gu", "targetLanguageName": "Gujarati", "targetScriptCode": "Gujr"},
    {"sourceLanguage": "kn", "sourceLanguageName": "Kannada", "sourceScriptCode": "Knda", "targetLanguage": "kn", "targetLanguageName": "Kannada", "targetScriptCode": "Knda"},
    {"sourceLanguage": "ml", "sourceLanguageName": "Malayalam", "sourceScriptCode": "Mlym", "targetLanguage": "ml", "targetLanguageName": "Malayalam", "targetScriptCode": "Mlym"},
    {"sourceLanguage": "pa", "sourceLanguageName": "Punjabi", "sourceScriptCode": "Guru", "targetLanguage": "pa", "targetLanguageName": "Punjabi", "targetScriptCode": "Guru"},
    {"sourceLanguage": "or", "sourceLanguageName": "Odia", "sourceScriptCode": "Orya", "targetLanguage": "or", "targetLanguageName": "Odia", "targetScriptCode": "Orya"},
]

# Previous source-only shape, kept so downgrade() can restore it exactly.
LLM_LANGUAGES_OLD = [{"sourceLanguage": l["sourceLanguage"]} for l in LLM_LANGUAGES]

LLM_ADAPTER_CONFIG = {
    "model_name": "google/gemma-4-31B-it",
    "inputs": [
        {"dtype": "BYTES", "shape": [1, 1], "tensor": "INPUT_TEXT", "value_path": "input.source"},
        {"dtype": "BYTES", "shape": [1, 1], "tensor": "INPUT_LANGUAGE_ID", "value_path": "request.config.language.sourceLanguage"},
        {"dtype": "BYTES", "shape": [1, 1], "tensor": "OUTPUT_LANGUAGE_ID", "value_path": "request.config.language.targetLanguage"},
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
            WHERE name = 'llm'
        """),
        {
            "languages": json.dumps(LLM_LANGUAGES),
            "request_language": json.dumps({"sourceLanguage": "hi", "targetLanguage": "hi"}),
            "adapter_config": json.dumps(LLM_ADAPTER_CONFIG),
        },
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
                inference_endpoint = jsonb_set(
                    inference_endpoint - 'adapterConfig',
                    '{schema,request,config}',
                    '{}'::jsonb,
                    true
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE name = 'llm'
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
