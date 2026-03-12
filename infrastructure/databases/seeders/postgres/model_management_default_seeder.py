"""
Model Management Default Seeder
Seeds default AI models and services for all task types in model_management_db.
All endpoint URLs are read from .env via app_env — no hardcoded URLs.
"""
from infrastructure.databases.core.base_seeder import BaseSeeder
from ai4icore_env import app_env
import hashlib
import time
import uuid


def generate_model_id(model_name: str, version: str) -> str:
    normalized_name = model_name.strip().lower()
    normalized_version = version.strip().lower()
    return hashlib.sha256(f"{normalized_name}:{normalized_version}".encode("utf-8")).hexdigest()[:32]


def generate_service_id(model_name: str, model_version: str, service_name: str) -> str:
    normalized_model_name = model_name.strip().lower()
    normalized_model_version = model_version.strip().lower()
    normalized_service_name = service_name.strip().lower()
    raw = f"{normalized_model_name}:{normalized_model_version}:{normalized_service_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def generate_uuid(*parts: str) -> str:
    raw = ":".join(part.strip().lower() for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


# Model/service definitions — endpoint comes from app_env at runtime
MODELS = [
    {
        "name": "asr_am_ensemble",
        "version": "1.0.0",
        "description": "Automatic Speech Recognition model for Hindi language using Conformer architecture.",
        "task_type": "asr",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}]',
        "domain": '["general", "conversational"]',
        "license": "Apache-2.0",
        "endpoint_attr": "triton_endpoint_asr",
        "services": [
            {
                "name": "asr-hindi-prod",
                "description": "Production ASR service for Hindi.",
                "hardware": "GPU: NVIDIA T4, RAM: 16GB",
            }
        ],
    },
    {
        "name": "tts",
        "version": "1.0.0",
        "description": "Text-to-Speech model for Hindi language using FastPitch architecture.",
        "task_type": "tts",
        "languages": '[{"sourceLanguage": "hi"}]',
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_tts",
        "services": [
            {
                "name": "tts-hindi-prod",
                "description": "Production TTS service for Hindi.",
                "hardware": "GPU: NVIDIA T4, RAM: 16GB",
            }
        ],
    },
    {
        "name": "nmt",
        "version": "1.0.0",
        "description": "Neural Machine Translation model for English to Hindi using IndicTrans2.",
        "task_type": "nmt",
        "languages": '[{"sourceLanguage": "en", "targetLanguage": "hi"}]',
        "domain": '["general", "news", "conversational"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_nmt",
        "services": [
            {
                "name": "nmt-en-hi-prod",
                "description": "Production NMT service for English-Hindi translation.",
                "hardware": "GPU: NVIDIA A10, RAM: 32GB",
            }
        ],
    },
    {
        "name": "ai4bharat/indictrans",
        "version": "1.0.0",
        "description": "IndicTrans - Neural Machine Translation model supporting multiple Indic languages.",
        "task_type": "nmt",
        "languages": '[{"sourceLanguage": "en", "targetLanguage": "hi"}, {"sourceLanguage": "hi", "targetLanguage": "en"}]',
        "domain": '["general", "news", "conversational"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_nmt",
        "services": [
            {
                "name": "gpu-t4",
                "description": "IndicTrans NMT service on GPU T4.",
                "hardware": "GPU: NVIDIA T4, RAM: 16GB",
            }
        ],
    },
    {
        "name": "llm",
        "version": "1.0.0",
        "description": "Large Language Model for Indic languages chat/completion.",
        "task_type": "llm",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}, {"sourceLanguage": "pa"}, {"sourceLanguage": "or"}]',
        "domain": '["general", "conversational", "qa"]',
        "license": "Apache-2.0",
        "endpoint_attr": "triton_endpoint_llm",
        "services": [
            {
                "name": "llm-indic-prod",
                "description": "Production LLM service for Indic languages.",
                "hardware": "GPU: NVIDIA A100, RAM: 80GB",
            }
        ],
    },
    {
        "name": "transliteration",
        "version": "1.0.0",
        "description": "Transliteration model for Indic scripts using IndicXlit.",
        "task_type": "transliteration",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}, {"sourceLanguage": "pa"}, {"sourceLanguage": "or"}]',
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_transliteration",
        "services": [
            {
                "name": "xlit-indic-prod",
                "description": "Production Transliteration service.",
                "hardware": "CPU: 8 cores, RAM: 16GB",
            }
        ],
    },
    {
        "name": "indiclid",
        "version": "1.0.0",
        "description": "Text language detection model for Indic languages.",
        "task_type": "language-detection",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}, {"sourceLanguage": "pa"}, {"sourceLanguage": "or"}]',
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_langdetect",
        "services": [
            {
                "name": "langdetect-prod",
                "description": "Production Language Detection service.",
                "hardware": "CPU: 4 cores, RAM: 8GB",
            }
        ],
    },
    {
        "name": "speaker_diarization",
        "version": "1.0.0",
        "description": "Speaker diarization model using Pyannote.",
        "task_type": "speaker-diarization",
        "languages": '[{"sourceLanguage": "*"}]',
        "domain": '["general", "meetings", "podcasts"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_speaker_diarization",
        "services": [
            {
                "name": "speaker-diarize-prod",
                "description": "Production Speaker Diarization service.",
                "hardware": "GPU: NVIDIA T4, RAM: 16GB",
            }
        ],
    },
    {
        "name": "AudioLangDetect-Whisper",
        "version": "1.0.0",
        "description": "Audio language detection model using Whisper.",
        "task_type": "audio-lang-detection",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}]',
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_audio_langdetect",
        "services": [
            {
                "name": "audio-langdetect-prod",
                "description": "Production Audio Language Detection service.",
                "hardware": "GPU: NVIDIA T4, RAM: 16GB",
            }
        ],
    },
    {
        "name": "lang_diarization",
        "version": "1.0.0",
        "description": "Language diarization model for multi-language audio.",
        "task_type": "language-diarization",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}]',
        "domain": '["code-switching", "multilingual"]',
        "license": "Apache-2.0",
        "endpoint_attr": "triton_endpoint_lang_diarization",
        "services": [
            {
                "name": "lang-diarize-prod",
                "description": "Production Language Diarization service.",
                "hardware": "GPU: NVIDIA T4, RAM: 16GB",
            }
        ],
    },
    {
        "name": "surya_ocr",
        "version": "1.0.0",
        "description": "Optical Character Recognition model for Indic scripts.",
        "task_type": "ocr",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}]',
        "domain": '["documents", "handwritten", "printed"]',
        "license": "Apache-2.0",
        "endpoint_attr": "triton_endpoint_ocr",
        "services": [
            {
                "name": "ocr-indic-prod",
                "description": "Production OCR service for Indic scripts.",
                "hardware": "GPU: NVIDIA T4, RAM: 16GB",
            }
        ],
    },
    {
        "name": "ner",
        "version": "1.0.0",
        "description": "Named Entity Recognition model for Indic languages.",
        "task_type": "ner",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}]',
        "domain": '["general", "news", "legal"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_ner",
        "services": [
            {
                "name": "ner-indic-prod",
                "description": "Production NER service for Indic languages.",
                "hardware": "CPU: 8 cores, RAM: 16GB",
            }
        ],
    },
]


class ModelManagementDefaultSeeder(BaseSeeder):
    """Seed default models and services for model_management_db."""

    database = 'model_management_db'

    def run(self, adapter):
        """Run the seeder."""
        timestamp_ms = int(time.time() * 1000)

        print("    Seeding models and services...")

        for m in MODELS:
            name = m["name"]
            version = m["version"]
            task_type = m["task_type"]
            endpoint_url = getattr(app_env, m["endpoint_attr"], "") or ""
            model_id = generate_model_id(name, version)

            adapter.execute(f"""
                INSERT INTO models (id, model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
                VALUES (
                    '{generate_uuid("model", name, version)}',
                    '{model_id}',
                    '{version}',
                    '{name}',
                    '{m["description"]}',
                    '{{"type": "{task_type}"}}'::jsonb,
                    '{m["languages"]}'::jsonb,
                    '{m["domain"]}'::jsonb,
                    '{m["license"]}',
                    '{{"schema": {{"modelProcessingType": {{"type": "{task_type}"}}, "model_name": "{name}", "request": {{}}, "response": {{}}}}, "callbackUrl": "{endpoint_url}"}}'::jsonb,
                    '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "aboutMe": null}}]}}'::jsonb,
                    {timestamp_ms},
                    'ACTIVE'
                ) ON CONFLICT (name, version) DO UPDATE SET
                    inference_endpoint = jsonb_set(
                        COALESCE(models.inference_endpoint, '{{}}'::jsonb),
                        '{{schema,model_name}}',
                        '"{name}"'::jsonb,
                        true
                    ),
                    updated_at = CURRENT_TIMESTAMP;
            """)

            for svc in m["services"]:
                svc_name = svc["name"]
                service_id = generate_service_id(name, version, svc_name)

                adapter.execute(f"""
                    INSERT INTO services (id, service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
                    VALUES (
                        '{generate_uuid("service", name, version, svc_name)}',
                        '{service_id}',
                        '{svc_name}',
                        '{model_id}',
                        '{version}',
                        '{endpoint_url}',
                        '{svc["description"]}',
                        '{svc["hardware"]}',
                        {timestamp_ms},
                        false
                    ) ON CONFLICT (model_id, model_version, name) DO UPDATE SET
                        endpoint = '{endpoint_url}',
                        updated_at = CURRENT_TIMESTAMP;
                """)

            print(f"    ✓ {name} model and service(s)")

        print("")
        print("    ════════════════════════════════════════════════════════════")
        print(f"    ✅ Seeded {len(MODELS)} models and services for all AI task types")
        print("    ════════════════════════════════════════════════════════════")
