"""
mm_services Seeder (ai4iplatform_core)

Inserts default AI service rows into mm_services.
Depends on mm_models_seeder having run first (FK: model_id → mm_models.model_id).
Discovery order is guaranteed: sorted *_seeder.py filenames place this seeder
alphabetically after mm_models_seeder.py.
"""
from infrastructure.databases.core.base_seeder import BaseSeeder
from infrastructure.databases.seeders.postgres.ai4iplatform_core._models_data import (
    MODELS,
    SEEDER_ID,
    _sql_lit,
    generate_model_id,
    generate_service_id,
    generate_uuid,
)

try:
    from ai4icore_env import app_env
except ImportError:
    app_env = None  # type: ignore[assignment]


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
            endpoint_url = (getattr(app_env, m["endpoint_attr"], "") or "") if app_env else ""
            model_id = generate_model_id(name, version)
            ep_lit = _sql_lit(endpoint_url)
            ist = "http" if task_type == "llm" else "triton"

            for svc in m["services"]:
                svc_name = svc["name"]
                service_id = generate_service_id(svc_name)
                sn = _sql_lit(svc_name)
                is_published = str(svc.get("is_published", True)).lower()

                adapter.execute(f"""
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
                        '{generate_uuid("service", name, version, svc_name)}',
                        '{service_id}',
                        '{sn}',
                        '{_sql_lit(svc["description"])}',
                        '{_sql_lit(svc["hardware"])}',
                        '{model_id}',
                        '{_sql_lit(version)}',
                        '{ep_lit}',
                        '{ist}',
                        true,
                        {is_published},
                        '{SEEDER_ID}'
                    )
                    ON CONFLICT (name) DO UPDATE SET
                        service_id            = '{service_id}',
                        service_description   = '{_sql_lit(svc["description"])}',
                        hardware_description  = '{_sql_lit(svc["hardware"])}',
                        model_id              = '{model_id}',
                        model_version         = '{_sql_lit(version)}',
                        endpoint              = '{ep_lit}',
                        inference_server_type = '{ist}',
                        ssl_verify            = true,
                        is_published          = {is_published},
                        updated_at            = CURRENT_TIMESTAMP;
                """)

                print(f"    ✓ {svc_name} → {name} ({task_type}, published={is_published})")
                total += 1

        print("")
        print("    ════════════════════════════════════════════════════════════")
        print(f"    ✅ Seeded {total} rows into mm_services")
        print("    ════════════════════════════════════════════════════════════")
