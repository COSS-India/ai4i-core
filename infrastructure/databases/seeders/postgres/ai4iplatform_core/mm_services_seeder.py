"""
mm_services Seeder (ai4iplatform_core)

Inserts default AI service rows into mm_services.
Depends on mm_models_seeder having run first (FK: model_id → mm_models.model_id).
Discovery order is guaranteed: sorted *_seeder.py filenames place this seeder
alphabetically after mm_models_seeder.py.
"""
import os

from infrastructure.databases.core.base_seeder import BaseSeeder
from infrastructure.databases.seeders.postgres.ai4iplatform_core._models_data import (
    MODELS,
    SEEDER_ID,
    generate_model_id,
    generate_service_id,
    generate_uuid,
)


class MmServicesSeeder(BaseSeeder):
    """Seed default AI service rows into mm_services."""

    database = "ai4iplatform_core"

    def run(self, adapter):
        print("    Seeding mm_services...")

        total = 0
        for m in MODELS:
            name = m["name"]
            version = m["version"]
            task_type = m["task_type"]
            endpoint_url = os.getenv(m["endpoint_attr"].upper(), "")
            model_id = generate_model_id(name, version)
            ist = "http" if task_type == "llm" else "triton"

            for svc in m["services"]:
                svc_name = svc["name"]
                service_id = generate_service_id(svc_name)
                is_published = svc.get("is_published", True)

                adapter.execute(
                    """
                    INSERT INTO mm_services (
                        id,
                        service_id,
                        name,
                        service_description,
                        hardware_description,
                        model_id,
                        model_version,
                        endpoint,
                        inference_server_type,
                        ssl_verify,
                        is_published,
                        created_by
                    )
                    VALUES (
                        :id,
                        :service_id,
                        :name,
                        :service_description,
                        :hardware_description,
                        :model_id,
                        :model_version,
                        :endpoint,
                        :inference_server_type,
                        true,
                        :is_published,
                        :created_by
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
                    """,
                    {
                        "id": generate_uuid("service", name, version, svc_name),
                        "service_id": service_id,
                        "name": svc_name,
                        "service_description": svc["description"],
                        "hardware_description": svc["hardware"],
                        "model_id": model_id,
                        "model_version": version,
                        "endpoint": endpoint_url,
                        "inference_server_type": ist,
                        "is_published": is_published,
                        "created_by": SEEDER_ID,
                    },
                )

                print(f"    ✓ {svc_name} → {name} ({task_type}, published={is_published})")
                total += 1

        print("")
        print("    ════════════════════════════════════════════════════════════")
        print(f"    ✅ Seeded {total} rows into mm_services")
        print("    ════════════════════════════════════════════════════════════")
