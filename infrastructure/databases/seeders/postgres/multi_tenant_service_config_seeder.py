from infrastructure.databases.core.base_seeder import BaseSeeder

class MultiTenantServiceConfigSeeder(BaseSeeder):
    """Seed service configuration and pricing for multi-tenant platform in multi_tenant_db."""
    
    database = 'multi_tenant_db'  # Target database
    
    def run(self, adapter):
        """Run the seeder."""
        service_configs = [
            (1, 'asr', 'minute', 0.001),
            (2, 'tts', 'character', 0.002),
            (3, 'nmt', 'character', 0.0001),
            (4, 'llm', 'request', 0.005),
            (5, 'ocr', 'request', 0.003),
            (6, 'ner', 'character', 0.0002),
            (7, 'language_detection', 'request', 0.00005),
            (8, 'transliteration', 'character', 0.0001),
            (9, 'speaker_diarization', 'minute', 0.005),
            (10, 'audio_language_detection', 'minute', 0.001),
            (11, 'pipeline', 'request', 0.01),
            (12, 'language_diarization', 'minute', 0.005),
        ]

        for config_id, service_name, unit_type, price_per_unit in service_configs:
            adapter.execute(
                """
                INSERT INTO service_config (
                    id,
                    service_name,
                    unit_type,
                    price_per_unit,
                    currency,
                    is_active
                )
                VALUES (
                    :id,
                    :service_name,
                    :unit_type,
                    :price_per_unit,
                    :currency,
                    :is_active
                )
                ON CONFLICT (service_name) DO NOTHING
                """,
                {
                    "id": config_id,
                    "service_name": service_name,
                    "unit_type": unit_type,
                    "price_per_unit": price_per_unit,
                    "currency": "INR",
                    "is_active": True,
                },
            )

        print(f"    ✓ Inserted {len(service_configs)} service configurations")
