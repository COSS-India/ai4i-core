"""seed_default_data

Revision ID: d3e850228f7e
Revises: 908da7983d98
Create Date: 2026-05-18 15:50:06.556387

"""
import hashlib
import json
import os
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3e850228f7e'
down_revision: Union[str, None] = '908da7983d98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

_SUBMITTER = json.dumps({
    "name": "AI4Bharat",
    "aboutMe": "AI research organization",
    "team": [{"name": "Admin", "aboutMe": None}],
})


def _generate_model_id(model_name: str, version: str) -> str:
    return hashlib.sha256(
        f"{model_name.strip().lower()}:{version.strip().lower()}".encode()
    ).hexdigest()[:32]


def _generate_service_id(service_name: str) -> str:
    return hashlib.sha256(
        service_name.strip().lower().encode()
    ).hexdigest()[:32]


def _generate_uuid(*parts: str) -> str:
    raw = ":".join(p.strip().lower() for p in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


MODELS = [
    {
        "name": "indiclid",
        "version": "1.0.0",
        "triton_model_name": "indiclid",
        "description": (
            "Indic Language Identification for text. Supports 47 language classes "
            "(24 native-script, 21 roman-script, plus English and Others). Uses "
            "IndicLID-FTN, IndicLID-FTR, and IndicLID-BERT based on "
            "ai4bharat/IndicBERTv2-MLM-only. Input: INPUT_TEXT (STRING). "
            "Output: OUTPUT_TEXT (STRING). Python backend, max batch 64, 1 GPU, "
            "dynamic batching."
        ),
        "task_type": "language-detection",
        "languages": (
            '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, '
            '{"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, '
            '{"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}, '
            '{"sourceLanguage": "pa"}, {"sourceLanguage": "or"}]'
        ),
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_langdetect",
        "request_schema": {"inputs": [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["नमस्ते, यह एक उदाहरण वाक्य है।"]}], "outputs": [{"name": "OUTPUT_TEXT"}]},
        "triton_schema": {"inputs": [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["नमस्ते, यह एक उदाहरण वाक्य है।"]}], "outputs": [{"name": "OUTPUT_TEXT"}]},
        "services": [{"name": "indiclid-gpu", "description": "IndicLID Triton service. Language identification for Indic languages. HTTP: 8000, gRPC: 8001, Metrics: 8002.", "hardware": "GPU: 1 instance, max batch 64, dynamic batching."}],
    },
    {
        "name": "ald",
        "version": "1.0.0",
        "triton_model_name": "ald",
        "description": "Audio Language Detection from speech audio. Uses SpeechBrain EncoderClassifier. Input: AUDIO_DATA (STRING). Output: LANGUAGE_CODE (STRING), CONFIDENCE (FP32), ALL_SCORES (STRING). Python backend, max batch 64, 1 GPU, dynamic batching.",
        "task_type": "audio-lang-detection",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}]',
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_audio_langdetect",
        "request_schema": {"audio": [{"audioContent": ""}], "config": {}},
        "triton_schema": {"inputs": [{"name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1]}], "outputs": [{"name": "LANGUAGE_CODE"}, {"name": "CONFIDENCE"}, {"name": "ALL_SCORES"}]},
        "services": [{"name": "ald-gpu", "description": "ALD Triton service. Audio language detection from speech. HTTP: 8100, gRPC: 8101, Metrics: 8102.", "hardware": "GPU: 1 instance, max batch 64, dynamic batching."}],
    },
    {
        "name": "surya-ocr",
        "version": "1.0.0",
        "triton_model_name": "surya_ocr",
        "description": "Surya OCR for document images. OCR in 90+ languages using Surya OCR models (Foundation, Detection, Recognition). Input: IMAGE_DATA (STRING). Output: OUTPUT_TEXT (STRING). Python backend, max batch 8, 1 GPU, dynamic batching.",
        "task_type": "ocr",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}]',
        "domain": '["documents", "handwritten", "printed"]',
        "license": "Apache-2.0",
        "endpoint_attr": "triton_endpoint_ocr",
        "request_schema": {"image": [{"imageContent": ""}], "config": {"language": {"sourceLanguage": "hi"}}},
        "triton_schema": {"inputs": [{"name": "IMAGE_DATA", "datatype": "BYTES", "shape": [1, 1]}], "outputs": [{"name": "OUTPUT_TEXT"}]},
        "services": [{"name": "surya-ocr-gpu", "description": "Surya OCR Triton service. OCR on document images. HTTP: 8400, gRPC: 8401, Metrics: 8402.", "hardware": "GPU: 1 instance, max batch 8, dynamic batching."}],
    },
    {
        "name": "ner",
        "version": "1.0.0",
        "triton_model_name": "ner",
        "description": "Named Entity Recognition for Indian languages. Model: ai4bharat/IndicNER. Supports 11 Indian languages. Input: INPUT_TEXT (STRING), LANG_ID (STRING). Output: OUTPUT_TEXT (STRING). Python backend, max batch 64, 1 GPU, dynamic batching.",
        "task_type": "ner",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}]',
        "domain": '["general", "news", "legal"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_ner",
        "request_schema": {"input": [{"source": "राम दिल्ली गए।"}], "config": {"language": {"sourceLanguage": "hi"}}},
        "triton_schema": {"inputs": [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["राम दिल्ली गए।"]}, {"name": "LANG_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"]}], "outputs": [{"name": "OUTPUT_TEXT"}]},
        "services": [{"name": "ner-gpu", "description": "NER Triton service. Named Entity Recognition for Indian languages. HTTP: 8300, gRPC: 8301, Metrics: 8302.", "hardware": "GPU: 1 instance, max batch 64, dynamic batching."}],
    },
    {
        "name": "speaker-diarization",
        "version": "1.0.0",
        "triton_model_name": "speaker_diarization",
        "description": "Speaker diarization from audio. Input: AUDIO_DATA (STRING), NUM_SPEAKERS (STRING, optional). Output: DIARIZATION_RESULT (STRING). Python backend, max batch 16, 1 GPU, dynamic batching.",
        "task_type": "speaker-diarization",
        "languages": '[{"sourceLanguage": "*"}]',
        "domain": '["general", "meetings", "podcasts"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_speaker_diarization",
        "request_schema": {"audio": [{"audioContent": ""}], "config": {}},
        "triton_schema": {"inputs": [{"name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1]}, {"name": "NUM_SPEAKERS", "datatype": "BYTES", "shape": [1, 1], "data": [""]}], "outputs": [{"name": "DIARIZATION_RESULT"}]},
        "services": [{"name": "sd-gpu", "description": "Speaker Diarization Triton service. Speaker diarization from audio. HTTP: 8700, gRPC: 8701, Metrics: 8702.", "hardware": "GPU: 1 instance, max batch 16, dynamic batching."}],
    },
    {
        "name": "lang-diarization",
        "version": "1.0.0",
        "triton_model_name": "lang_diarization",
        "description": "Language diarization from audio. Uses SpeechBrain EncoderClassifier for language identification. Input: AUDIO_DATA (STRING), LANGUAGE (STRING). Output: DIARIZATION_RESULT (STRING). Python backend, max batch 32, 1 GPU, dynamic batching.",
        "task_type": "language-diarization",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}]',
        "domain": '["code-switching", "multilingual"]',
        "license": "Apache-2.0",
        "endpoint_attr": "triton_endpoint_lang_diarization",
        "request_schema": {"audio": [{"audioContent": ""}], "config": {}},
        "triton_schema": {"inputs": [{"name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1]}, {"name": "LANGUAGE", "datatype": "BYTES", "shape": [1, 1], "data": [""]}], "outputs": [{"name": "DIARIZATION_RESULT"}]},
        "services": [{"name": "lang-diarization-gpu", "description": "Language Diarization Triton service. Language diarization from audio. HTTP: 8600, gRPC: 8601, Metrics: 8602.", "hardware": "GPU: 1 instance, max batch 32, dynamic batching."}],
    },
    {
        "name": "transliteration",
        "version": "1.0.0",
        "triton_model_name": "transliteration",
        "description": "Indic Transliteration (Indic-Xlit). English-to-Indic and Indic-to-English using ai4bharat.transliteration.XlitEngine. Input: INPUT_TEXT (STRING), INPUT_LANGUAGE_ID (STRING), OUTPUT_LANGUAGE_ID (STRING), IS_WORD_LEVEL (BOOL), TOP_K (UINT8). Output: OUTPUT_TEXT (STRING). Python backend, 1 CPU instance (only CPU model in inventory).",
        "task_type": "transliteration",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}, {"sourceLanguage": "pa"}, {"sourceLanguage": "or"}]',
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_transliteration",
        "request_schema": {"input": [{"source": "namaste"}], "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "en"}}},
        "triton_schema": {"inputs": [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1], "data": ["namaste"]}, {"name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1], "data": ["hi"]}, {"name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1], "data": ["en"]}, {"name": "IS_WORD_LEVEL", "datatype": "BOOL", "shape": [1], "data": [False]}, {"name": "TOP_K", "datatype": "UINT8", "shape": [1], "data": [0]}], "outputs": [{"name": "OUTPUT_TEXT"}]},
        "services": [{"name": "indic-xlit-cpu", "description": "Indic-Xlit Triton service. Transliteration between English and Indic languages. HTTP: 8200, gRPC: 8201, Metrics: 8202.", "hardware": "CPU: 1 instance."}],
    },
    {
        "name": "asr-am-ensemble",
        "version": "1.0.0",
        "triton_model_name": "asr_am_ensemble",
        "description": "Multilingual ASR ensemble for end-to-end speech-to-text over multiple Indic languages. Primary Triton model: asr_am_ensemble (ensemble backend). Pipeline: asr_preprocessor → asr_am → asr_greedy_decoder. Uses CTC decoding via pyctcdecode and exposes top-k decoding via asr_am_topk_ensemble. Input: AUDIO_SIGNAL (FP32, [-1, -1]), NUM_SAMPLES (INT32, [-1, 1]), LANG_ID (STRING/BYTES, [-1, 1]). Output: TRANSCRIPTS (STRING/BYTES, [-1, -1]).",
        "task_type": "asr",
        "languages": '[{"sourceLanguage": "as"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "brx"}, {"sourceLanguage": "doi"}, {"sourceLanguage": "kok"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "hi"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ks"}, {"sourceLanguage": "mai"}, {"sourceLanguage": "ml"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "mni"}, {"sourceLanguage": "ne"}, {"sourceLanguage": "or"}, {"sourceLanguage": "pa"}, {"sourceLanguage": "sa"}, {"sourceLanguage": "sat"}, {"sourceLanguage": "sd"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "ur"}]',
        "domain": '["general", "conversational"]',
        "license": "Apache-2.0",
        "endpoint_attr": "triton_endpoint_asr",
        "request_schema": {"audio": [{"audioContent": ""}], "config": {"language": {"sourceLanguage": "hi"}}},
        "triton_schema": {"inputs": [{"name": "AUDIO_SIGNAL", "datatype": "FP32", "shape": [1, 4000], "data": [0.0]}, {"name": "NUM_SAMPLES", "datatype": "INT32", "shape": [1, 1], "data": [4000]}, {"name": "LANG_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"]}], "outputs": [{"name": "TRANSCRIPTS"}]},
        "services": [{"name": "asr-gpu", "description": "Multilingual ASR Triton service (ai4bharat/triton-multilingual-asr:latest). HTTP: 5000, gRPC: 5001, Metrics: 5002. Runs asr_preprocessor (PyTorch, GPU), asr_am (ONNXRuntime, GPU), and asr_greedy_decoder (Python, CPU) as an ensemble.", "hardware": "GPU: 1 instance (encoder + preprocessing), CPU: 1 instance (decoder), dynamic batching (up to batch 32 for encoder, 512 for preprocessor)."}],
    },
    {
        "name": "tts",
        "version": "1.0.0",
        "triton_model_name": "tts",
        "description": "Indo-Aryan TTS model to generate speech waveforms from text using FastPitch + HiFiGAN per language. Checkpoints loaded from /models/checkpoints/<lang_code>/. Supported speaker IDs: male, female. Supported languages (minimum): as, bn, gu, hi, mr, or, pa, raj. Input: INPUT_TEXT, INPUT_SPEAKER_ID, INPUT_LANGUAGE_ID (STRING/BYTES, [1]). Output: OUTPUT_GENERATED_AUDIO (FP32, [-1]).",
        "task_type": "tts",
        "languages": '[{"sourceLanguage": "as"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "hi"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "or"}, {"sourceLanguage": "pa"}, {"sourceLanguage": "raj"}]',
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_tts",
        "request_schema": {"input": [{"source": "नमस्ते"}], "config": {"language": {"sourceLanguage": "hi"}, "gender": "female"}},
        "triton_schema": {"inputs": [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1], "data": ["namaste"]}, {"name": "INPUT_SPEAKER_ID", "datatype": "BYTES", "shape": [1], "data": ["female"]}, {"name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1], "data": ["hi"]}], "outputs": [{"name": "OUTPUT_GENERATED_AUDIO"}]},
        "services": [{"name": "indo-aryan-tts-gpu", "description": "Indo-Aryan TTS Triton service (ai4bharat/triton-indo-aryan-tts:latest). HTTP: 9000, gRPC: 9001, Metrics: 9002. Uses FastPitch and HiFiGAN per language to synthesize speech from text.", "hardware": "GPU: 1 instance, max batch size 0."}],
    },
    {
        "name": "indictrans",
        "version": "1.0.0",
        "triton_model_name": "nmt",
        "description": "IndicTrans NMT model supporting multiple Indic languages.",
        "task_type": "nmt",
        "languages": '[{"sourceLanguage": "en", "targetLanguage": "hi"}, {"sourceLanguage": "hi", "targetLanguage": "en"}]',
        "domain": '["general", "news", "conversational"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_nmt",
        "request_schema": {"input": [{"source": "Hello, how are you?"}], "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}}},
        "triton_schema": {"inputs": [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["Hello, how are you?"]}, {"name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["en"]}, {"name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"]}], "outputs": [{"name": "OUTPUT_TEXT"}]},
        "services": [{"name": "indictrans-gpu-t4", "description": "IndicTrans NMT service on GPU T4.", "hardware": "GPU: NVIDIA T4, RAM: 16GB"}],
    },
    {
        "name": "llm",
        "version": "1.0.0",
        "triton_model_name": "llm",
        "description": "Large Language Model for Indic languages chat/completion.",
        "task_type": "llm",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}, {"sourceLanguage": "pa"}, {"sourceLanguage": "or"}]',
        "domain": '["general", "conversational", "qa"]',
        "license": "Apache-2.0",
        "endpoint_attr": "triton_endpoint_llm",
        "request_schema": {"input": [{"source": "Hello"}], "config": {}},
        "triton_schema": {"inputs": [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["Hello"]}, {"name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"]}, {"name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"]}], "outputs": [{"name": "OUTPUT_TEXT"}]},
        "services": [{"name": "llm-indic-prod", "description": "Production LLM service for Indic languages.", "hardware": "GPU: NVIDIA A100, RAM: 80GB", "is_published": False}],
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    for m in MODELS:
        name              = m["name"]
        version           = m["version"]
        task_type         = m["task_type"]
        triton_model_name = m.get("triton_model_name", name)
        endpoint_url      = os.getenv(m["endpoint_attr"].upper(), "")
        model_id          = _generate_model_id(name, version)

        inference_endpoint = {
            "schema": {
                "modelProcessingType": {"type": task_type},
                "model_name": triton_model_name,
                "request": m.get("request_schema", {}),
                "response": {"triton": m.get("triton_schema") or {}},
            },
            "callbackUrl": endpoint_url,
        }

        conn.execute(
            sa.text("""
                INSERT INTO mm_models (
                    id, model_id, version, version_status, name, description,
                    task, languages, domain, license, inference_endpoint,
                    submitter, created_by
                ) VALUES (
                    :id, :model_id, :version, 'ACTIVE', :name, :description,
                    CAST(:task AS jsonb), CAST(:languages AS jsonb),
                    CAST(:domain AS jsonb), :license,
                    CAST(:inference_endpoint AS jsonb),
                    CAST(:submitter AS jsonb), :created_by
                )
                ON CONFLICT (name, version) DO UPDATE SET
                    inference_endpoint = CAST(:inference_endpoint AS jsonb),
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "id":                 _generate_uuid("model", name, version),
                "model_id":           model_id,
                "version":            version,
                "name":               name,
                "description":        m["description"],
                "task":               json.dumps({"type": task_type}),
                "languages":          m["languages"],
                "domain":             m["domain"],
                "license":            m["license"],
                "inference_endpoint": json.dumps(inference_endpoint),
                "submitter":          _SUBMITTER,
                "created_by":         SEEDER_ID,
            },
        )

        ist = "http" if task_type == "llm" else "triton"
        for svc in m["services"]:
            svc_name   = svc["name"]
            service_id = _generate_service_id(svc_name)

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
                        :endpoint, :inference_server_type, true,
                        :is_published, :created_by
                    )
                    ON CONFLICT (name) DO UPDATE SET
                        service_id            = :service_id,
                        service_description   = :service_description,
                        hardware_description  = :hardware_description,
                        model_id              = :model_id,
                        model_version         = :model_version,
                        endpoint              = :endpoint,
                        inference_server_type = :inference_server_type,
                        ssl_verify            = true,
                        is_published          = :is_published,
                        updated_at            = CURRENT_TIMESTAMP
                """),
                {
                    "id":                  _generate_uuid("service", name, version, svc_name),
                    "service_id":          service_id,
                    "name":                svc_name,
                    "service_description": svc["description"],
                    "hardware_description":svc["hardware"],
                    "model_id":            model_id,
                    "model_version":       version,
                    "endpoint":            endpoint_url,
                    "inference_server_type": ist,
                    "is_published":        svc.get("is_published", True),
                    "created_by":          SEEDER_ID,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM mm_services WHERE created_by = :sid"), {"sid": SEEDER_ID})
    conn.execute(sa.text("DELETE FROM mm_models WHERE created_by = :sid"), {"sid": SEEDER_ID})
