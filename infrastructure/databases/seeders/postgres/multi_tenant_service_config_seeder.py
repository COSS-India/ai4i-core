from infrastructure.databases.core.base_seeder import BaseSeeder

class MultiTenantServiceConfigSeeder(BaseSeeder):
    """Seed service configuration and pricing for multi-tenant platform in multi_tenant_db."""
    
    database = 'multi_tenant_db'  # Target database
    
    def run(self, adapter):
        """Run the seeder."""
        # Insert service configurations with pricing
        adapter.execute("""
            INSERT INTO service_config (service_name, display_name, description, base_price, pricing_model, features, is_active)
            VALUES
            (
                'asr',
                'Automatic Speech Recognition',
                'Convert speech to text in multiple Indian languages',
                0.001,
                'PAY_PER_MINUTE',
                '{"languages": ["en", "hi", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa"], "max_duration": "3600", "formats": ["wav", "mp3", "flac"]}'::jsonb,
                true
            ),
            (
                'tts',
                'Text-to-Speech',
                'Convert text to natural speech in multiple Indian languages',
                0.002,
                'PAY_PER_CHARACTER',
                '{"languages": ["en", "hi", "ta", "te", "bn"], "voices": ["male", "female"], "max_length": "5000"}'::jsonb,
                true
            ),
            (
                'nmt',
                'Neural Machine Translation',
                'Translate text between Indian languages',
                0.0001,
                'PAY_PER_CHARACTER',
                '{"language_pairs": ["en-hi", "hi-en", "en-ta", "ta-en", "en-te", "te-en"], "max_length": "5000"}'::jsonb,
                true
            ),
            (
                'llm',
                'Large Language Model',
                'AI-powered text generation and question answering',
                0.005,
                'PAY_PER_TOKEN',
                '{"models": ["gpt-indic"], "max_tokens": "4096", "temperature_range": [0.0, 2.0]}'::jsonb,
                true
            ),
            (
                'ocr',
                'Optical Character Recognition',
                'Extract text from images and documents in Indian languages',
                0.003,
                'PAY_PER_IMAGE',
                '{"languages": ["en", "hi", "ta", "te", "bn"], "max_size_mb": "10", "formats": ["jpg", "png", "pdf"]}'::jsonb,
                true
            ),
            (
                'ner',
                'Named Entity Recognition',
                'Identify and extract named entities from text',
                0.0002,
                'PAY_PER_CHARACTER',
                '{"languages": ["en", "hi"], "entity_types": ["PERSON", "ORGANIZATION", "LOCATION", "DATE", "TIME"], "max_length": "10000"}'::jsonb,
                true
            ),
            (
                'language_detection',
                'Language Detection',
                'Automatically detect the language of input text',
                0.00005,
                'PAY_PER_REQUEST',
                '{"supported_languages": 22, "confidence_threshold": 0.95}'::jsonb,
                true
            ),
            (
                'transliteration',
                'Transliteration',
                'Convert text between different scripts',
                0.0001,
                'PAY_PER_CHARACTER',
                '{"script_pairs": ["devanagari-latin", "latin-devanagari"], "max_length": "5000"}'::jsonb,
                true
            ),
            (
                'speaker_diarization',
                'Speaker Diarization',
                'Identify and separate different speakers in audio',
                0.005,
                'PAY_PER_MINUTE',
                '{"max_speakers": 10, "max_duration": "1800", "formats": ["wav", "mp3"]}'::jsonb,
                true
            ),
            (
                'audio_lang_detection',
                'Audio Language Detection',
                'Detect the language spoken in audio files',
                0.001,
                'PAY_PER_MINUTE',
                '{"supported_languages": 15, "confidence_threshold": 0.90}'::jsonb,
                true
            )
            ON CONFLICT (service_name) DO NOTHING;
        """)
        print("    ✓ Inserted 10 service configurations with pricing")
