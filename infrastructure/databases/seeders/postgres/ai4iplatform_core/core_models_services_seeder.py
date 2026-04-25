"""
Core Models and Services Seeder (ai4iplatform_core)

Seeds default AI models and services into ai4iplatform_core.
Mirrors model_management_default_seeder.py but targets the newer schema:
  - mm_models  (vs models in model_management_db)
  - mm_services (vs services in model_management_db)

Schema differences:
  - mm_models:  no submitted_on (uses created_at server_default); has ref_url, benchmarks
  - mm_services: published_at (DATETIME) instead of published_on (INT); has api_key,
                 health_status, benchmarks, policy, unpublished_at (all nullable)

Model/service definitions are shared with model_management_default_seeder to keep
a single source of truth.
"""
import json
import time

from infrastructure.databases.core.base_seeder import BaseSeeder
from infrastructure.databases.seeders.postgres.model_management_default_seeder import (
    MODELS,
    _sql_lit,
    generate_model_id,
    generate_service_id,
    generate_uuid,
)

try:
    from ai4icore_env import app_env
except ImportError:
    app_env = None  # type: ignore[assignment]

# Fixed identity for all rows written by seeders — readable as "seed0000…"
SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


class CoreModelsServicesSeeder(BaseSeeder):
    """Seed default models and services for ai4iplatform_core (mm_models / mm_services)."""

    database = "ai4iplatform_core"

    def run(self, adapter):
        print("    Seeding mm_models and mm_services...")

        for m in MODELS:
            name = m["name"]
            version = m["version"]
            task_type = m["task_type"]
            triton_model_name = m.get("triton_model_name", name)
            endpoint_url = (getattr(app_env, m["endpoint_attr"], "") or "") if app_env else ""
            model_id = generate_model_id(name, version)

            request_schema = m.get("request_schema", {})
            inference_endpoint = {
                "schema": {
                    "modelProcessingType": {"type": task_type},
                    "model_name": triton_model_name,
                    "request": request_schema,
                    "response": {},
                },
                "callbackUrl": endpoint_url,
            }

            ep_lit = _sql_lit(endpoint_url)
            tn_lit = _sql_lit(triton_model_name)
            inference_endpoint_lit = _sql_lit(
                json.dumps(inference_endpoint, ensure_ascii=False, separators=(",", ":"))
            )

            # ── mm_models ───────────────────────────────────────────────────
            adapter.execute(f"""
                INSERT INTO mm_models (
                    id, model_id, version, name, description,
                    task, languages, domain, license,
                    inference_endpoint, submitter, version_status, created_by
                )
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
                    '{inference_endpoint_lit}'::jsonb,
                    '{{"name": "AI4Bharat", "aboutMe": "AI research organization", "team": [{{"name": "Admin", "aboutMe": null}}]}}'::jsonb,
                    'ACTIVE',
                    '{SEEDER_ID}'
                )
                ON CONFLICT (name, version) DO UPDATE SET
                    inference_endpoint       = '{inference_endpoint_lit}'::jsonb,
                    updated_at               = CURRENT_TIMESTAMP;
            """)

            # ── mm_services ─────────────────────────────────────────────────
            for svc in m["services"]:
                svc_name = svc["name"]
                service_id = generate_service_id(svc_name)
                sn = _sql_lit(svc_name)
                ist = "http" if task_type == "llm" else "triton"

                adapter.execute(f"""
                    INSERT INTO mm_services (
                        id, service_id, name,
                        model_id, model_version,
                        endpoint, inference_server_type, ssl_verify,
                        service_description, hardware_description,
                        is_published, created_by
                    )
                    VALUES (
                        '{generate_uuid("service", name, version, svc_name)}',
                        '{service_id}',
                        '{sn}',
                        '{model_id}',
                        '{_sql_lit(version)}',
                        '{ep_lit}',
                        '{ist}',
                        true,
                        '{_sql_lit(svc["description"])}',
                        '{_sql_lit(svc["hardware"])}',
                        true,
                        '{SEEDER_ID}'
                    )
                    ON CONFLICT (name) DO UPDATE SET
                        service_id          = '{service_id}',
                        model_id            = '{model_id}',
                        model_version       = '{_sql_lit(version)}',
                        endpoint            = '{ep_lit}',
                        inference_server_type = '{ist}',
                        ssl_verify          = true,
                        service_description = '{_sql_lit(svc["description"])}',
                        hardware_description = '{_sql_lit(svc["hardware"])}',
                        is_published        = true,
                        updated_at          = CURRENT_TIMESTAMP;
                """)

            print(f"    ✓ {name} ({task_type})")

        print("")
        print("    ════════════════════════════════════════════════════════════")
        print(f"    ✅ Seeded {len(MODELS)} models and services into ai4iplatform_core")
        print("    ════════════════════════════════════════════════════════════")
