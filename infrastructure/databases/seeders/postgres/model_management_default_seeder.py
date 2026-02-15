from infrastructure.databases.core.base_seeder import BaseSeeder


class ModelManagementDefaultSeeder(BaseSeeder):
    """Seed default models and services for model_management_db."""
    
    database = 'model_management_db'  # Target database
    
    def run(self, adapter):
        """Run the seeder."""
        # Insert default AI models with all required fields
        import time
        timestamp_ms = int(time.time() * 1000)
        
        adapter.execute(f"""
            INSERT INTO models (
                model_id, version, version_status, submitted_on, name, description,
                task, languages, domain, inference_endpoint, submitter, created_by, updated_by
            )
            VALUES
            (
                'ai4bharat-indicwav2vec-base',
                'v1.0',
                'ACTIVE',
                {timestamp_ms},
                'IndicWav2Vec Base',
                'Speech recognition model for Indian languages',
                '{{"type": "asr"}}'::jsonb,
                '["hi", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "or"]'::jsonb,
                '["general"]'::jsonb,
                '{{"callbackUrl": "http://asr-service:8001"}}'::jsonb,
                '{{"name": "system", "oauthId": "system"}}'::jsonb,
                'system',
                'system'
            ),
            (
                'ai4bharat-indictts',
                'v1.0',
                'ACTIVE',
                {timestamp_ms},
                'IndicTTS',
                'Text-to-speech model for Indian languages',
                '{{"type": "tts"}}'::jsonb,
                '["hi", "ta", "te", "bn", "mr"]'::jsonb,
                '["general"]'::jsonb,
                '{{"callbackUrl": "http://tts-service:8002"}}'::jsonb,
                '{{"name": "system", "oauthId": "system"}}'::jsonb,
                'system',
                'system'
            ),
            (
                'ai4bharat-indictrans-v2',
                'v2.0',
                'ACTIVE',
                {timestamp_ms},
                'IndicTrans v2',
                'Neural machine translation for Indian languages',
                '{{"type": "translation"}}'::jsonb,
                '["hi", "ta", "te", "en"]'::jsonb,
                '["general"]'::jsonb,
                '{{"callbackUrl": "http://nmt-service:8003"}}'::jsonb,
                '{{"name": "system", "oauthId": "system"}}'::jsonb,
                'system',
                'system'
            ),
            (
                'tesseract-indic',
                'v5.0',
                'ACTIVE',
                {timestamp_ms},
                'Tesseract Indic',
                'OCR model for Indian language scripts',
                '{{"type": "ocr"}}'::jsonb,
                '["hi", "ta", "te", "bn", "mr"]'::jsonb,
                '["document"]'::jsonb,
                '{{"callbackUrl": "http://ocr-service:8005"}}'::jsonb,
                '{{"name": "system", "oauthId": "system"}}'::jsonb,
                'system',
                'system'
            )
            ON CONFLICT ON CONSTRAINT uq_name_version DO NOTHING;
        """)
        print("    ✓ Inserted 4 default AI models")
        
        # Note: Services table has complex structure with model_id FK
        # Skipping services seeder as it requires existing model UUIDs
        # Services will be registered dynamically by the application
        print("    ℹ️  Skipped services (requires model UUIDs)")
