"""
Model Management Default Seeder
Seeds default AI models and services for all task types in model_management_db.
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


def generate_service_id(service_name: str) -> str:
    normalized_service_name = service_name.strip().lower()
    return hashlib.sha256(normalized_service_name.encode("utf-8")).hexdigest()[:32]


def generate_uuid(*parts: str) -> str:
    raw = ":".join(part.strip().lower() for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def _sql_lit(value: str) -> str:
    """Escape single quotes for PostgreSQL string literals in raw SQL."""
    return value.replace("'", "''")

# Model/service definitions — endpoint comes from app_env at runtime
MODELS = [
    {
        "name": "indiclid",
        "version": "1.0.0",
        "triton_model_name": "indiclid",
        "description": "Indic Language Identification for text. Supports 47 language classes (24 native-script, 21 roman-script, plus English and Others). Uses IndicLID-FTN, IndicLID-FTR, and IndicLID-BERT based on ai4bharat/IndicBERTv2-MLM-only. Input: INPUT_TEXT (STRING). Output: OUTPUT_TEXT (STRING). Python backend, max batch 64, 1 GPU, dynamic batching.",
        "task_type": "language-detection",
        "languages": '[{"sourceLanguage": "hi"}, {"sourceLanguage": "en"}, {"sourceLanguage": "ta"}, {"sourceLanguage": "te"}, {"sourceLanguage": "bn"}, {"sourceLanguage": "mr"}, {"sourceLanguage": "gu"}, {"sourceLanguage": "kn"}, {"sourceLanguage": "ml"}, {"sourceLanguage": "pa"}, {"sourceLanguage": "or"}]',
        "domain": '["general"]',
        "license": "MIT",
        "endpoint_attr": "triton_endpoint_langdetect",
        "services": [
            {
                "name": "indiclid-gpu",
                "description": "IndicLID Triton service. Language identification for Indic languages. HTTP: 8000, gRPC: 8001, Metrics: 8002.",
                "hardware": "GPU: 1 instance, max batch 64, dynamic batching.",
            }
        ],
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
        "services": [
            {
                "name": "ald-gpu",
                "description": "ALD Triton service. Audio language detection from speech. HTTP: 8100, gRPC: 8101, Metrics: 8102.",
                "hardware": "GPU: 1 instance, max batch 64, dynamic batching.",
            }
        ],
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
        "services": [
            {
                "name": "surya-ocr-gpu",
                "description": "Surya OCR Triton service. OCR on document images. HTTP: 8400, gRPC: 8401, Metrics: 8402.",
                "hardware": "GPU: 1 instance, max batch 8, dynamic batching.",
            }
        ],
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
        "services": [
            {
                "name": "ner-gpu",
                "description": "NER Triton service. Named Entity Recognition for Indian languages. HTTP: 8300, gRPC: 8301, Metrics: 8302.",
                "hardware": "GPU: 1 instance, max batch 64, dynamic batching.",
            }
        ],
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
        "services": [
            {
                "name": "sd-gpu",
                "description": "Speaker Diarization Triton service. Speaker diarization from audio. HTTP: 8700, gRPC: 8701, Metrics: 8702.",
                "hardware": "GPU: 1 instance, max batch 16, dynamic batching.",
            }
        ],
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
        "services": [
            {
                "name": "lang-diarization-gpu",
                "description": "Language Diarization Triton service. Language diarization from audio. HTTP: 8600, gRPC: 8601, Metrics: 8602.",
                "hardware": "GPU: 1 instance, max batch 32, dynamic batching.",
            }
        ],
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
        "services": [
            {
                "name": "indic-xlit-cpu",
                "description": "Indic-Xlit Triton service. Transliteration between English and Indic languages. HTTP: 8200, gRPC: 8201, Metrics: 8202.",
                "hardware": "CPU: 1 instance.",
            }
        ],
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
        "services": [
            {
                "name": "asr-gpu",
                "description": "Multilingual ASR Triton service (ai4bharat/triton-multilingual-asr:latest). HTTP: 5000, gRPC: 5001, Metrics: 5002. Runs asr_preprocessor (PyTorch, GPU), asr_am (ONNXRuntime, GPU), and asr_greedy_decoder (Python, CPU) as an ensemble.",
                "hardware": "GPU: 1 instance (encoder + preprocessing), CPU: 1 instance (decoder), dynamic batching (up to batch 32 for encoder, 512 for preprocessor).",
            }
        ],
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
        "services": [
            {
                "name": "indo-aryan-tts-gpu",
                "description": "Indo-Aryan TTS Triton service (ai4bharat/triton-indo-aryan-tts:latest). HTTP: 9000, gRPC: 9001, Metrics: 9002. Uses FastPitch and HiFiGAN per language to synthesize speech from text.",
                "hardware": "GPU: 1 instance, max batch size 0.",
            }
        ],
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
        "services": [
            {
                "name": "indictrans-gpu-t4",
                "description": "IndicTrans NMT service on GPU T4.",
                "hardware": "GPU: NVIDIA T4, RAM: 16GB",
            }
        ],
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
        "services": [
            {
                "name": "llm-indic-prod",
                "description": "Production LLM service for Indic languages.",
                "hardware": "GPU: NVIDIA A100, RAM: 80GB",
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
            triton_model_name = m.get("triton_model_name", name)
            endpoint_url = getattr(app_env, m["endpoint_attr"], "") or ""
            model_id = generate_model_id(name, version)

            ep = _sql_lit(endpoint_url)
            tn = _sql_lit(triton_model_name)
            adapter.execute(f"""
                INSERT INTO models (id, model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
                VALUES (
                    '{generate_uuid("model", name, version)}',
                    '{model_id}',
                    '{_sql_lit(version)}',
                    '{_sql_lit(name)}',
                    '{_sql_lit(m["description"])}',
                    '{{"type": "{task_type}"}}'::jsonb,
                    '{_sql_lit(m["languages"])}'::jsonb,
                    '{_sql_lit(m["domain"])}'::jsonb,
                    '{_sql_lit(m["license"])}',
                    '{{"schema": {{"modelProcessingType": {{"type": "{task_type}"}}, "model_name": "{tn}", "request": {{}}, "response": {{}}}}, "callbackUrl": "{ep}"}}'::jsonb,
                    '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "aboutMe": null}}]}}'::jsonb,
                    {timestamp_ms},
                    'ACTIVE'
                ) ON CONFLICT (name, version) DO UPDATE SET
                    inference_endpoint = jsonb_set(
                        COALESCE(models.inference_endpoint, '{{}}'::jsonb),
                        '{{schema,model_name}}',
                        '"{tn}"'::jsonb,
                        true
                    ),
                    updated_at = CURRENT_TIMESTAMP;
            """)

            for svc in m["services"]:
                svc_name = svc["name"]
                service_id = generate_service_id(svc_name)

                sn = _sql_lit(svc_name)
                adapter.execute(f"""
                    INSERT INTO services (id, service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
                    VALUES (
                        '{generate_uuid("service", name, version, svc_name)}',
                        '{service_id}',
                        '{sn}',
                        '{model_id}',
                        '{_sql_lit(version)}',
                        '{ep}',
                        '{_sql_lit(svc["description"])}',
                        '{_sql_lit(svc["hardware"])}',
                        {timestamp_ms},
                        false
                    ) ON CONFLICT (name) DO UPDATE SET
                        service_id = '{service_id}',
                        model_id = '{model_id}',
                        model_version = '{_sql_lit(version)}',
                        endpoint = '{ep}',
                        service_description = '{_sql_lit(svc["description"])}',
                        hardware_description = '{_sql_lit(svc["hardware"])}',
                        updated_at = CURRENT_TIMESTAMP;
                """)

            print(f"    ✓ {name} model and service(s)")

        print("")
        print("    ════════════════════════════════════════════════════════════")
        print(f"    ✅ Seeded {len(MODELS)} models and services for all AI task types")
        print("    ════════════════════════════════════════════════════════════")
