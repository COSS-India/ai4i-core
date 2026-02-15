"""
Create AI Services Indexes and Triggers Migration
Creates indexes and triggers for all AI service tables in auth_db
"""
from infrastructure.migrations.core.base_migration import BaseMigration


class CreateAiServicesIndexes(BaseMigration):
    """Create indexes and triggers for AI service tables"""
    
    def up(self, adapter):
        """Run migration"""
        # ASR indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_asr_requests_user_id ON asr_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_asr_requests_status ON asr_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_asr_requests_created_at ON asr_requests(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_asr_results_request_id ON asr_results(request_id)",
            
            # TTS indexes
            "CREATE INDEX IF NOT EXISTS idx_tts_requests_user_id ON tts_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_tts_requests_status ON tts_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_tts_requests_created_at ON tts_requests(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_tts_results_request_id ON tts_results(request_id)",
            
            # NMT indexes
            "CREATE INDEX IF NOT EXISTS idx_nmt_requests_user_id ON nmt_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_nmt_requests_status ON nmt_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_nmt_requests_created_at ON nmt_requests(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_nmt_results_request_id ON nmt_results(request_id)",
            
            # LLM indexes
            "CREATE INDEX IF NOT EXISTS idx_llm_requests_user_id ON llm_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_llm_requests_status ON llm_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_llm_requests_created_at ON llm_requests(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_llm_results_request_id ON llm_results(request_id)",
            
            # OCR indexes
            "CREATE INDEX IF NOT EXISTS idx_ocr_requests_user_id ON ocr_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_ocr_requests_status ON ocr_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_ocr_requests_created_at ON ocr_requests(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_ocr_results_request_id ON ocr_results(request_id)",
            
            # NER indexes
            "CREATE INDEX IF NOT EXISTS idx_ner_requests_user_id ON ner_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_ner_requests_status ON ner_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_ner_requests_created_at ON ner_requests(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_ner_results_request_id ON ner_results(request_id)",
        ]
        
        for idx in indexes:
            adapter.execute(idx)
        print("    ✓ Created all indexes for AI services")
        
        # Create triggers for updated_at columns
        triggers = [
            ("asr_requests", "update_asr_requests_updated_at"),
            ("tts_requests", "update_tts_requests_updated_at"),
            ("nmt_requests", "update_nmt_requests_updated_at"),
            ("llm_requests", "update_llm_requests_updated_at"),
            ("ocr_requests", "update_ocr_requests_updated_at"),
            ("ner_requests", "update_ner_requests_updated_at"),
            ("language_detection_requests", "update_language_detection_requests_updated_at"),
            ("transliteration_requests", "update_transliteration_requests_updated_at"),
            ("speaker_diarization_requests", "update_speaker_diarization_requests_updated_at"),
            ("language_diarization_requests", "update_language_diarization_requests_updated_at"),
            ("audio_lang_detection_requests", "update_audio_lang_detection_requests_updated_at"),
        ]
        
        for table, trigger_name in triggers:
            adapter.execute(f"""
                CREATE TRIGGER {trigger_name}
                    BEFORE UPDATE ON {table}
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column()
            """)
        
        print("    ✓ Created all triggers for AI services")
    
    def down(self, adapter):
        """Rollback migration"""
        # Drop triggers
        triggers = [
            "update_asr_requests_updated_at",
            "update_tts_requests_updated_at",
            "update_nmt_requests_updated_at",
            "update_llm_requests_updated_at",
            "update_ocr_requests_updated_at",
            "update_ner_requests_updated_at",
            "update_language_detection_requests_updated_at",
            "update_transliteration_requests_updated_at",
            "update_speaker_diarization_requests_updated_at",
            "update_language_diarization_requests_updated_at",
            "update_audio_lang_detection_requests_updated_at",
        ]
        
        for trigger_name in triggers:
            adapter.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {trigger_name.replace('update_', '').replace('_updated_at', '')} CASCADE")
        
        print("    ✓ Dropped all triggers and indexes")
