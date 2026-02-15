"""
Create AI Services Triggers Migration
Adds updated_at triggers for all AI service request tables
"""
from infrastructure.databases.core.base_migration import BaseMigration


class CreateAiServicesTriggers(BaseMigration):
    """Create updated_at triggers for AI service tables"""
    
    def up(self, adapter):
        """Run migration"""
        print("    Creating AI services updated_at triggers...")
        
        # Create triggers for all AI service request tables
        ai_service_tables = [
            "asr_requests",
            "tts_requests",
            "nmt_requests",
            "llm_requests",
            "language_detection_requests",
            "transliteration_requests",
            "ocr_requests",
            "ner_requests",
            "speaker_diarization_requests",
            "language_diarization_requests",
            "audio_lang_detection_requests"
        ]
        
        for table in ai_service_tables:
            trigger_name = f"update_{table}_updated_at"
            adapter.execute(f"""
                DROP TRIGGER IF EXISTS {trigger_name} ON {table};
                CREATE TRIGGER {trigger_name}
                    BEFORE UPDATE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            """)
            print(f"    ✓ Created {trigger_name} trigger")
        
    def down(self, adapter):
        """Rollback migration"""
        print("    Dropping AI services updated_at triggers...")
        
        ai_service_tables = [
            "asr_requests",
            "tts_requests",
            "nmt_requests",
            "llm_requests",
            "language_detection_requests",
            "transliteration_requests",
            "ocr_requests",
            "ner_requests",
            "speaker_diarization_requests",
            "language_diarization_requests",
            "audio_lang_detection_requests"
        ]
        
        for table in ai_service_tables:
            trigger_name = f"update_{table}_updated_at"
            adapter.execute(f"""
                DROP TRIGGER IF EXISTS {trigger_name} ON {table};
            """)
            print(f"    ✓ Dropped {trigger_name} trigger")
