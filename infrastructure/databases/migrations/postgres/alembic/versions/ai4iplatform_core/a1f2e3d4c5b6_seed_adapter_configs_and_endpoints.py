"""seed_adapter_configs_and_endpoints

Adds adapter_config to all mm_models inference_endpoint, updates mm_services
endpoints from env vars, and seeds the two extra NMT services that the base
seeder omits.

Revision ID: a1f2e3d4c5b6
Revises: 9c2a7b4e1f5d
Create Date: 2026-06-04 10:00:00.000000

"""
import hashlib
import json
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1f2e3d4c5b6'
down_revision: Union[str, None] = '9c2a7b4e1f5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def _generate_model_id(model_name: str, version: str) -> str:
    return hashlib.sha256(
        f"{model_name.strip().lower()}:{version.strip().lower()}".encode()
    ).hexdigest()[:32]


def _generate_service_id(service_name: str) -> str:
    return hashlib.sha256(
        service_name.strip().lower().encode()
    ).hexdigest()[:32]


import uuid as _uuid_mod


def _generate_uuid(*parts: str) -> str:
    raw = ":".join(p.strip().lower() for p in parts)
    return str(_uuid_mod.uuid5(_uuid_mod.NAMESPACE_URL, raw))


# ---------------------------------------------------------------------------
# adapter_config per model — sourced from dev infra mm_models.inference_endpoint
# ---------------------------------------------------------------------------
ADAPTER_CONFIGS = {
    "asr-am-ensemble": {
        "inputs": [
            {"dtype": "FP32",  "shape": [-1, -1], "tensor": "AUDIO_SIGNAL",  "value_path": "audio.samples"},
            {"dtype": "INT32", "shape": [-1, 1],  "tensor": "NUM_SAMPLES",   "value_path": "audio.num_samples"},
            {"dtype": "BYTES", "shape": [-1, 1],  "tensor": "LANG_ID",       "value_path": "request.config.language.source_language"},
        ],
        "outputs": [{"dtype": "BYTES", "tensor": "TRANSCRIPTS", "maps_to": "transcript"}],
        "version": "1.0", "model_version": "1",
    },
    "ald": {
        "inputs": [
            {"dtype": "BYTES", "shape": [1, 1], "tensor": "AUDIO_DATA", "value_path": "audio.audio_content"},
        ],
        "outputs": [
            {"dtype": "BYTES", "tensor": "LANGUAGE_CODE", "maps_to": "language_code"},
            {"dtype": "FP32",  "tensor": "CONFIDENCE",    "maps_to": "confidence"},
            {"dtype": "BYTES", "tensor": "ALL_SCORES",    "maps_to": "all_scores"},
        ],
        "version": "1.0", "model_version": "1",
    },
    "indiclid": {
        "inputs": [
            {"dtype": "BYTES", "shape": [-1, 1], "tensor": "INPUT_TEXT", "value_path": "input.source"},
        ],
        "outputs": [{"dtype": "BYTES", "tensor": "OUTPUT_TEXT", "maps_to": "langPrediction"}],
        "version": "1.0", "model_version": "1",
    },
    "lang-diarization": {
        "inputs": [
            {"dtype": "BYTES", "shape": [1, 1], "tensor": "AUDIO_DATA", "value_path": "audio.audio_content"},
            {"dtype": "BYTES", "shape": [1, 1], "tensor": "LANGUAGE",   "value_path": "request.config.target_language"},
        ],
        "outputs": [{"dtype": "BYTES", "tensor": "DIARIZATION_RESULT", "maps_to": "diarization_json"}],
        "version": "1.0", "model_version": "1",
    },
    "ner": {
        "inputs": [
            {"dtype": "BYTES", "shape": [-1, 1], "tensor": "INPUT_TEXT", "value_path": "input.source"},
            {"dtype": "BYTES", "shape": [-1, 1], "tensor": "LANG_ID",    "value_path": "request.config.language.sourceLanguage"},
        ],
        "outputs": [{"dtype": "BYTES", "tensor": "OUTPUT_TEXT", "maps_to": "target"}],
        "version": "1.0", "model_version": "1",
    },
    "surya-ocr": {
        "inputs": [
            {"dtype": "BYTES", "shape": [-1, 1], "tensor": "IMAGE_DATA", "value_path": "input.image_content"},
        ],
        "outputs": [{"dtype": "BYTES", "tensor": "OUTPUT_TEXT", "maps_to": "text"}],
        "version": "1", "model_version": "1",
    },
    "speaker-diarization": {
        "inputs": [
            {"dtype": "BYTES", "shape": [1, 1], "tensor": "AUDIO_DATA",    "value_path": "audio.audio_content"},
            {"dtype": "BYTES", "shape": [1, 1], "tensor": "NUM_SPEAKERS",  "value_path": "request.config.num_speakers"},
        ],
        "outputs": [{"dtype": "BYTES", "tensor": "DIARIZATION_RESULT", "maps_to": "diarization_json"}],
        "version": "1.0", "model_version": "1",
    },
    "transliteration": {
        "inputs": [
            {"dtype": "BYTES", "shape": [-1], "tensor": "INPUT_TEXT",         "value_path": "input.source"},
            {"dtype": "BYTES", "shape": [-1], "tensor": "INPUT_LANGUAGE_ID",  "value_path": "request.config.language.sourceLanguage"},
            {"dtype": "BYTES", "shape": [-1], "tensor": "OUTPUT_LANGUAGE_ID", "value_path": "request.config.language.targetLanguage"},
            {"dtype": "BOOL",  "shape": [-1], "tensor": "IS_WORD_LEVEL",      "value_path": "request.config.is_word_level"},
            {"dtype": "UINT8", "shape": [-1], "tensor": "TOP_K",              "value_path": "request.config.top_k"},
        ],
        "outputs": [{"dtype": "BYTES", "tensor": "OUTPUT_TEXT", "maps_to": "target"}],
        "version": "1.0", "model_version": "1",
    },
    "indictrans": {
        "inputs": [
            {"dtype": "BYTES", "shape": [-1, 1], "tensor": "INPUT_TEXT",         "value_path": "input.source"},
            {"dtype": "BYTES", "shape": [-1, 1], "tensor": "INPUT_LANGUAGE_ID",  "value_path": "request.config.language.source_language"},
            {"dtype": "BYTES", "shape": [-1, 1], "tensor": "OUTPUT_LANGUAGE_ID", "value_path": "request.config.language.target_language"},
        ],
        "outputs": [{"dtype": "BYTES", "tensor": "OUTPUT_TEXT", "maps_to": "target"}],
        "version": "1.0", "model_version": "1",
    },
    "tts": {
        "inputs": [
            {"dtype": "BYTES", "shape": [1], "tensor": "INPUT_TEXT",       "value_path": "input.source"},
            {"dtype": "BYTES", "shape": [1], "tensor": "INPUT_SPEAKER_ID", "value_path": "input.gender"},
            {"dtype": "BYTES", "shape": [1], "tensor": "INPUT_LANGUAGE_ID","value_path": "input.language_id"},
        ],
        "outputs": [{"dtype": "FP32", "tensor": "OUTPUT_GENERATED_AUDIO", "maps_to": "audio_data"}],
        "version": "1.0", "model_version": "1",
    },
}

# ---------------------------------------------------------------------------
# Extra NMT services missing from the base seeder
# ---------------------------------------------------------------------------
EXTRA_NMT_SERVICES = [
    {"name": "indictrans-nmt-service-2", "description": "IndicTrans NMT service 2.", "hardware": "GPU: NVIDIA T4, RAM: 16GB"},
    {"name": "NMT-Service-05",           "description": "NMT Service 05.",           "hardware": "GPU: NVIDIA T4, RAM: 16GB"},
]


def upgrade() -> None:
    conn = op.get_bind()

    nmt_endpoint = os.getenv("TRITON_ENDPOINT_NMT", "")

    # ── 1. Inject adapterConfig into inference_endpoint for each model ──
    for model_name, adapter_config in ADAPTER_CONFIGS.items():
        conn.execute(
            sa.text("""
                UPDATE mm_models
                SET inference_endpoint = inference_endpoint ||
                    jsonb_build_object('adapterConfig', CAST(:adapter_config AS jsonb))
                WHERE name = :model_name
            """),
            {
                "model_name":     model_name,
                "adapter_config": json.dumps(adapter_config),
            },
        )

    # ── 2. Update service endpoints from env vars ──
    endpoint_map = {
        "asr-gpu":              os.getenv("TRITON_ENDPOINT_ASR", ""),
        "ald-gpu":              os.getenv("TRITON_ENDPOINT_AUDIO_LANGDETECT", ""),
        "indiclid-gpu":         os.getenv("TRITON_ENDPOINT_LANGDETECT", ""),
        "lang-diarization-gpu": os.getenv("TRITON_ENDPOINT_LANG_DIARIZATION", ""),
        "ner-gpu":              os.getenv("TRITON_ENDPOINT_NER", ""),
        "surya-ocr-gpu":        os.getenv("TRITON_ENDPOINT_OCR", ""),
        "sd-gpu":               os.getenv("TRITON_ENDPOINT_SPEAKER_DIARIZATION", ""),
        "indic-xlit-cpu":       os.getenv("TRITON_ENDPOINT_TRANSLITERATION", ""),
        "indictrans-gpu-t4":    nmt_endpoint,
        "indo-aryan-tts-gpu":   os.getenv("TRITON_ENDPOINT_TTS", ""),
        "llm-indic-prod":       os.getenv("TRITON_ENDPOINT_LLM", ""),
    }

    for svc_name, endpoint in endpoint_map.items():
        if endpoint:
            conn.execute(
                sa.text("UPDATE mm_services SET endpoint = :endpoint WHERE name = :name"),
                {"endpoint": endpoint, "name": svc_name},
            )

    # ── 3. Seed extra NMT services ──
    nmt_model_id = _generate_model_id("indictrans", "1.0.0")

    for svc in EXTRA_NMT_SERVICES:
        conn.execute(
            sa.text("""
                INSERT INTO mm_services (
                    id, service_id, name, service_description,
                    hardware_description, model_id, model_version,
                    endpoint, inference_server_type, ssl_verify,
                    is_published, created_by
                ) VALUES (
                    :id, :service_id, :name, :service_description,
                    :hardware_description, :model_id, :model_version,
                    :endpoint, 'triton', true, true, :created_by
                )
                ON CONFLICT (name) DO UPDATE SET
                    endpoint   = :endpoint,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "id":                  _generate_uuid("service", "indictrans", "1.0.0", svc["name"]),
                "service_id":          _generate_service_id(svc["name"]),
                "name":                svc["name"],
                "service_description": svc["description"],
                "hardware_description":svc["hardware"],
                "model_id":            nmt_model_id,
                "model_version":       "1.0.0",
                "endpoint":            nmt_endpoint,
                "created_by":          SEEDER_ID,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Remove adapterConfig from inference_endpoint
    for model_name in ADAPTER_CONFIGS:
        conn.execute(
            sa.text("""
                UPDATE mm_models
                SET inference_endpoint = inference_endpoint - 'adapterConfig'
                WHERE name = :model_name
            """),
            {"model_name": model_name},
        )

    # Remove extra NMT services
    extra_names = [s["name"] for s in EXTRA_NMT_SERVICES]
    conn.execute(
        sa.text("DELETE FROM mm_services WHERE name = ANY(:names)"),
        {"names": extra_names},
    )
