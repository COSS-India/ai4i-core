"""
Model Management Default Seeder
Seeds default AI models and services for all task types in model_management_db
"""
from infrastructure.databases.core.base_seeder import BaseSeeder
import time


class ModelManagementDefaultSeeder(BaseSeeder):
    """Seed default models and services for model_management_db."""
    
    database = 'model_management_db'  # Target database
    
    def run(self, adapter):
        """Run the seeder."""
        # Get current timestamp in epoch milliseconds
        timestamp_ms = int(time.time() * 1000)
        
        print("    Seeding models and services...")
        
        # ========================================================================
        # 1. ASR (Automatic Speech Recognition) Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('asr_am_ensemble', '1.0.0'),
                '1.0.0',
                'asr_am_ensemble',
                'Automatic Speech Recognition model for Hindi language using Conformer architecture. UPDATE ENDPOINT before use.',
                '{{"type": "asr"}}'::jsonb,
                '["hi", "en"]'::jsonb,
                '["general", "conversational"]'::jsonb,
                'Apache-2.0',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8001/asr/v1/recognize"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('asr_am_ensemble', '1.0.0', 'asr-hindi-prod'),
                'asr-hindi-prod',
                generate_model_id('asr_am_ensemble', '1.0.0'),
                '1.0.0',
                'http://localhost:8001/asr/v1/recognize',
                'Production ASR service for Hindi. UPDATE ENDPOINT to your actual service URL.',
                'GPU: NVIDIA T4, RAM: 16GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ ASR model and service")
        
        # ========================================================================
        # 2. TTS (Text-to-Speech) Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('tts', '1.0.0'),
                '1.0.0',
                'tts',
                'Text-to-Speech model for Hindi language using FastPitch architecture. UPDATE ENDPOINT before use.',
                '{{"type": "tts"}}'::jsonb,
                '["hi"]'::jsonb,
                '["general"]'::jsonb,
                'MIT',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8002/tts/v1/synthesize"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('tts', '1.0.0', 'tts-hindi-prod'),
                'tts-hindi-prod',
                generate_model_id('tts', '1.0.0'),
                '1.0.0',
                'http://localhost:8002/tts/v1/synthesize',
                'Production TTS service for Hindi. UPDATE ENDPOINT to your actual service URL.',
                'GPU: NVIDIA T4, RAM: 16GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ TTS model and service")
        
        # ========================================================================
        # 3. NMT (Neural Machine Translation) Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('nmt', '1.0.0'),
                '1.0.0',
                'nmt',
                'Neural Machine Translation model for English to Hindi using IndicTrans2. UPDATE ENDPOINT before use.',
                '{{"type": "nmt"}}'::jsonb,
                '["en", "hi"]'::jsonb,
                '["general", "news", "conversational"]'::jsonb,
                'MIT',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8003/nmt/v1/translate"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('nmt', '1.0.0', 'nmt-en-hi-prod'),
                'nmt-en-hi-prod',
                generate_model_id('nmt', '1.0.0'),
                '1.0.0',
                'http://localhost:8003/nmt/v1/translate',
                'Production NMT service for English-Hindi translation. UPDATE ENDPOINT to your actual service URL.',
                'GPU: NVIDIA A10, RAM: 32GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ NMT model and service")
        
        # ========================================================================
        # 4. LLM (Large Language Model) Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('llm', '1.0.0'),
                '1.0.0',
                'llm',
                'Large Language Model for Indic languages chat/completion. UPDATE ENDPOINT before use.',
                '{{"type": "llm"}}'::jsonb,
                '["hi", "en", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "or"]'::jsonb,
                '["general", "conversational", "qa"]'::jsonb,
                'Apache-2.0',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8004/llm/v1/completions"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('llm', '1.0.0', 'llm-indic-prod'),
                'llm-indic-prod',
                generate_model_id('llm', '1.0.0'),
                '1.0.0',
                'http://localhost:8004/llm/v1/completions',
                'Production LLM service for Indic languages. UPDATE ENDPOINT to your actual service URL.',
                'GPU: NVIDIA A100, RAM: 80GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ LLM model and service")
        
        # ========================================================================
        # 5. Transliteration Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('transliteration', '1.0.0'),
                '1.0.0',
                'transliteration',
                'Transliteration model for Indic scripts using IndicXlit. UPDATE ENDPOINT before use.',
                '{{"type": "transliteration"}}'::jsonb,
                '["hi", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "or"]'::jsonb,
                '["general"]'::jsonb,
                'MIT',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8005/transliteration/v1/transliterate"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('transliteration', '1.0.0', 'xlit-indic-prod'),
                'xlit-indic-prod',
                generate_model_id('transliteration', '1.0.0'),
                '1.0.0',
                'http://localhost:8005/transliteration/v1/transliterate',
                'Production Transliteration service. UPDATE ENDPOINT to your actual service URL.',
                'CPU: 8 cores, RAM: 16GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ Transliteration model and service")
        
        # ========================================================================
        # 6. Language Detection Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('indiclid', '1.0.0'),
                '1.0.0',
                'indiclid',
                'Text language detection model for Indic languages. UPDATE ENDPOINT before use.',
                '{{"type": "language-detection"}}'::jsonb,
                '["hi", "en", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "or"]'::jsonb,
                '["general"]'::jsonb,
                'MIT',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8006/langdetect/v1/detect"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('indiclid', '1.0.0', 'langdetect-prod'),
                'langdetect-prod',
                generate_model_id('indiclid', '1.0.0'),
                '1.0.0',
                'http://localhost:8006/langdetect/v1/detect',
                'Production Language Detection service. UPDATE ENDPOINT to your actual service URL.',
                'CPU: 4 cores, RAM: 8GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ Language Detection model and service")
        
        # ========================================================================
        # 7. Speaker Diarization Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('speaker_diarization', '1.0.0'),
                '1.0.0',
                'speaker_diarization',
                'Speaker diarization model using Pyannote. UPDATE ENDPOINT before use.',
                '{{"type": "speaker-diarization"}}'::jsonb,
                '["*"]'::jsonb,
                '["general", "meetings", "podcasts"]'::jsonb,
                'MIT',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8007/speaker-diarization/v1/diarize"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('speaker_diarization', '1.0.0', 'speaker-diarize-prod'),
                'speaker-diarize-prod',
                generate_model_id('speaker_diarization', '1.0.0'),
                '1.0.0',
                'http://localhost:8007/speaker-diarization/v1/diarize',
                'Production Speaker Diarization service. UPDATE ENDPOINT to your actual service URL.',
                'GPU: NVIDIA T4, RAM: 16GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ Speaker Diarization model and service")
        
        # ========================================================================
        # 8. Audio Language Detection Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('AudioLangDetect-Whisper', '1.0.0'),
                '1.0.0',
                'AudioLangDetect-Whisper',
                'Audio language detection model using Whisper. UPDATE ENDPOINT before use.',
                '{{"type": "audio-lang-detection"}}'::jsonb,
                '["hi", "en", "ta", "te", "bn", "mr"]'::jsonb,
                '["general"]'::jsonb,
                'MIT',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8008/audio-langdetect/v1/detect"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('AudioLangDetect-Whisper', '1.0.0', 'audio-langdetect-prod'),
                'audio-langdetect-prod',
                generate_model_id('AudioLangDetect-Whisper', '1.0.0'),
                '1.0.0',
                'http://localhost:8008/audio-langdetect/v1/detect',
                'Production Audio Language Detection service. UPDATE ENDPOINT to your actual service URL.',
                'GPU: NVIDIA T4, RAM: 16GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ Audio Language Detection model and service")
        
        # ========================================================================
        # 9. Language Diarization Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('lang_diarization', '1.0.0'),
                '1.0.0',
                'lang_diarization',
                'Language diarization model for multi-language audio. UPDATE ENDPOINT before use.',
                '{{"type": "language-diarization"}}'::jsonb,
                '["hi", "en", "ta", "te"]'::jsonb,
                '["code-switching", "multilingual"]'::jsonb,
                'Apache-2.0',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8009/lang-diarization/v1/diarize"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('lang_diarization', '1.0.0', 'lang-diarize-prod'),
                'lang-diarize-prod',
                generate_model_id('lang_diarization', '1.0.0'),
                '1.0.0',
                'http://localhost:8009/lang-diarization/v1/diarize',
                'Production Language Diarization service. UPDATE ENDPOINT to your actual service URL.',
                'GPU: NVIDIA T4, RAM: 16GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ Language Diarization model and service")
        
        # ========================================================================
        # 10. OCR (Optical Character Recognition) Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('surya_ocr', '1.0.0'),
                '1.0.0',
                'surya_ocr',
                'Optical Character Recognition model for Indic scripts. UPDATE ENDPOINT before use.',
                '{{"type": "ocr"}}'::jsonb,
                '["hi", "ta", "te", "bn", "mr", "gu", "kn", "ml"]'::jsonb,
                '["documents", "handwritten", "printed"]'::jsonb,
                'Apache-2.0',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8010/ocr/v1/recognize"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('surya_ocr', '1.0.0', 'ocr-indic-prod'),
                'ocr-indic-prod',
                generate_model_id('surya_ocr', '1.0.0'),
                '1.0.0',
                'http://localhost:8010/ocr/v1/recognize',
                'Production OCR service for Indic scripts. UPDATE ENDPOINT to your actual service URL.',
                'GPU: NVIDIA T4, RAM: 16GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ OCR model and service")
        
        # ========================================================================
        # 11. NER (Named Entity Recognition) Model and Service
        # ========================================================================
        adapter.execute(f"""
            INSERT INTO models (model_id, version, name, description, task, languages, domain, license, inference_endpoint, submitter, submitted_on, version_status)
            VALUES (
                generate_model_id('ner', '1.0.0'),
                '1.0.0',
                'ner',
                'Named Entity Recognition model for Indic languages. UPDATE ENDPOINT before use.',
                '{{"type": "ner"}}'::jsonb,
                '["hi", "en", "ta", "te", "bn", "mr"]'::jsonb,
                '["general", "news", "legal"]'::jsonb,
                'MIT',
                '{{"schema": {{"request": {{}}, "response": {{}}}}, "callbackUrl": "http://localhost:8011/ner/v1/extract"}}'::jsonb,
                '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "role": "Maintainer"}}]}}'::jsonb,
                {timestamp_ms},
                'ACTIVE'
            ) ON CONFLICT (name, version) DO NOTHING;
        """)
        
        adapter.execute(f"""
            INSERT INTO services (service_id, name, model_id, model_version, endpoint, service_description, hardware_description, published_on, is_published)
            VALUES (
                generate_service_id('ner', '1.0.0', 'ner-indic-prod'),
                'ner-indic-prod',
                generate_model_id('ner', '1.0.0'),
                '1.0.0',
                'http://localhost:8011/ner/v1/extract',
                'Production NER service for Indic languages. UPDATE ENDPOINT to your actual service URL.',
                'CPU: 8 cores, RAM: 16GB',
                {timestamp_ms},
                false
            ) ON CONFLICT (model_id, model_version, name) DO NOTHING;
        """)
        print("    ✓ NER model and service")
        
        print("")
        print("    ════════════════════════════════════════════════════════════")
        print("    ✅ Seeded 11 models and 11 services for all AI task types")
        print("    ⚠️  IMPORTANT: Update endpoint URLs before publishing!")
        print("    ════════════════════════════════════════════════════════════")
