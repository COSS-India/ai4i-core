"""
Create AI Services Tables Migration
Creates tables for ASR, TTS, NMT, LLM, OCR, NER and other AI services in auth_db
"""
from infrastructure.databases.core.base_migration import BaseMigration


class CreateAiServicesTables(BaseMigration):
    """Create all AI service request and result tables"""
    
    def up(self, adapter):
        """Run migration"""
        # Enable UUID extension
        adapter.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\"")
        print("    ✓ Enabled pgcrypto extension")
        
        # ASR Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS asr_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                language VARCHAR(10) NOT NULL,
                audio_duration FLOAT,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS asr_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES asr_requests(id) ON DELETE CASCADE,
                transcript TEXT NOT NULL,
                confidence_score FLOAT CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
                word_timestamps JSONB,
                language_detected VARCHAR(10),
                audio_format VARCHAR(20),
                sample_rate INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created ASR tables")
        
        # TTS Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS tts_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                voice_id VARCHAR(50) NOT NULL,
                language VARCHAR(10) NOT NULL,
                text_length INTEGER,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS tts_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES tts_requests(id) ON DELETE CASCADE,
                audio_file_path TEXT NOT NULL,
                audio_duration FLOAT,
                audio_format VARCHAR(20),
                sample_rate INTEGER,
                bit_rate INTEGER,
                file_size INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created TTS tables")
        
        # NMT Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS nmt_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                source_language VARCHAR(10) NOT NULL,
                target_language VARCHAR(10) NOT NULL,
                text_length INTEGER,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS nmt_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES nmt_requests(id) ON DELETE CASCADE,
                translated_text TEXT NOT NULL,
                confidence_score FLOAT CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
                source_text TEXT,
                language_detected VARCHAR(10),
                word_alignments JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created NMT tables")
        
        # LLM Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS llm_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                input_language VARCHAR(10),
                output_language VARCHAR(10),
                text_length INTEGER,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS llm_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES llm_requests(id) ON DELETE CASCADE,
                output_text TEXT NOT NULL,
                source_text TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created LLM tables")
        
        # OCR Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS ocr_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                language VARCHAR(10) NOT NULL,
                image_count INTEGER,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS ocr_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES ocr_requests(id) ON DELETE CASCADE,
                extracted_text TEXT NOT NULL,
                page_count INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created OCR tables")
        
        # NER Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS ner_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                language VARCHAR(10) NOT NULL,
                text_length INTEGER,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS ner_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES ner_requests(id) ON DELETE CASCADE,
                entities JSONB NOT NULL,
                source_text TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created NER tables")
        
        # Language Detection Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS language_detection_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER,
                model_id VARCHAR(100) NOT NULL,
                text_length INTEGER,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS language_detection_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES language_detection_requests(id) ON DELETE CASCADE,
                source_text TEXT NOT NULL,
                detected_language VARCHAR(10) NOT NULL,
                detected_script VARCHAR(10) NOT NULL,
                confidence_score FLOAT NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
                language_name VARCHAR(100),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created Language Detection tables")
        
        # Transliteration Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS transliteration_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                source_language VARCHAR(10) NOT NULL,
                target_language VARCHAR(10) NOT NULL,
                text_length INTEGER,
                is_sentence_level BOOLEAN DEFAULT true,
                num_suggestions INTEGER DEFAULT 0,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS transliteration_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES transliteration_requests(id) ON DELETE CASCADE,
                transliterated_text JSONB NOT NULL,
                source_text TEXT,
                confidence_score FLOAT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created Transliteration tables")
        
        # Speaker Diarization Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS speaker_diarization_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                audio_duration FLOAT,
                num_speakers INTEGER,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS speaker_diarization_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES speaker_diarization_requests(id) ON DELETE CASCADE,
                total_segments INTEGER NOT NULL,
                num_speakers INTEGER NOT NULL,
                speakers JSONB NOT NULL,
                segments JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created Speaker Diarization tables")
        
        # Language Diarization Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS language_diarization_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                audio_duration FLOAT,
                target_language VARCHAR(10),
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS language_diarization_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES language_diarization_requests(id) ON DELETE CASCADE,
                total_segments INTEGER NOT NULL,
                segments JSONB NOT NULL,
                target_language VARCHAR(10),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created Language Diarization tables")
        
        # Audio Language Detection Tables
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS audio_lang_detection_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                model_id VARCHAR(100) NOT NULL,
                audio_duration FLOAT,
                processing_time FLOAT,
                status VARCHAR(20) DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        adapter.execute("""
            CREATE TABLE IF NOT EXISTS audio_lang_detection_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request_id UUID REFERENCES audio_lang_detection_requests(id) ON DELETE CASCADE,
                language_code VARCHAR(50) NOT NULL,
                confidence FLOAT CHECK (confidence >= 0.0 AND confidence <= 1.0),
                all_scores JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("    ✓ Created Audio Language Detection tables")
        
        print("    ✓ All AI service tables created successfully")
    
    def down(self, adapter):
        """Rollback migration"""
        # Drop all AI service tables
        tables = [
            'audio_lang_detection_results', 'audio_lang_detection_requests',
            'language_diarization_results', 'language_diarization_requests',
            'speaker_diarization_results', 'speaker_diarization_requests',
            'transliteration_results', 'transliteration_requests',
            'language_detection_results', 'language_detection_requests',
            'ner_results', 'ner_requests',
            'ocr_results', 'ocr_requests',
            'llm_results', 'llm_requests',
            'nmt_results', 'nmt_requests',
            'tts_results', 'tts_requests',
            'asr_results', 'asr_requests'
        ]
        
        for table in tables:
            adapter.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        
        print("    ✓ Dropped all AI service tables")
