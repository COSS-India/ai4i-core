"""
mm_models Seeder (ai4iplatform_core)

Inserts default AI model catalog rows into mm_models.
Must run before mm_services_seeder (FK: mm_services.model_id → mm_models.model_id).
Discovery order is guaranteed: sorted *_seeder.py filenames place this seeder
alphabetically before mm_services_seeder.py.
"""
import json

from infrastructure.databases.core.base_seeder import BaseSeeder
from infrastructure.databases.seeders.postgres.ai4iplatform_core._models_data import (
    MODELS,
    SEEDER_ID,
    generate_model_id,
    generate_uuid,
)

try:
    from ai4icore_env import app_env
except ImportError:
    app_env = None  # type: ignore[assignment]

_SUBMITTER = json.dumps({
    "name": "AI4Bharat",
    "aboutMe": "AI research organization",
    "team": [{"name": "Admin", "aboutMe": None}],
})


class MmModelsSeeder(BaseSeeder):
    """Seed default AI model catalog rows into mm_models."""

    database = "ai4iplatform_core"

    def run(self, adapter):
        print("    Seeding mm_models...")

        for m in MODELS:
            name = m["name"]
            version = m["version"]
            task_type = m["task_type"]
            triton_model_name = m.get("triton_model_name", name)
            endpoint_url = (getattr(app_env, m["endpoint_attr"], "") or "") if app_env else ""
            model_id = generate_model_id(name, version)

            inference_endpoint = {
                "schema": {
                    "modelProcessingType": {"type": task_type},
                    "model_name": triton_model_name,
                    "request": m.get("request_schema", {}),
                    "response": {
                        "triton": m.get("triton_schema") or {},
                    },
                },
                "callbackUrl": endpoint_url,
            }

            adapter.execute(
                """
                INSERT INTO mm_models (
                    id,
                    model_id,
                    version,
                    version_status,
                    name,
                    description,
                    task,
                    languages,
                    domain,
                    license,
                    inference_endpoint,
                    submitter,
                    created_by
                )
                VALUES (
                    :id,
                    :model_id,
                    :version,
                    'ACTIVE',
                    :name,
                    :description,
                    CAST(:task AS jsonb),
                    CAST(:languages AS jsonb),
                    CAST(:domain AS jsonb),
                    :license,
                    CAST(:inference_endpoint AS jsonb),
                    CAST(:submitter AS jsonb),
                    :created_by
                )
                ON CONFLICT (name, version) DO UPDATE SET
                    inference_endpoint = CAST(:inference_endpoint AS jsonb),
                    updated_at         = CURRENT_TIMESTAMP
                """,
                {
                    "id": generate_uuid("model", name, version),
                    "model_id": model_id,
                    "version": version,
                    "name": name,
                    "description": m["description"],
                    "task": json.dumps({"type": task_type}),
                    "languages": m["languages"],
                    "domain": m["domain"],
                    "license": m["license"],
                    "inference_endpoint": json.dumps(inference_endpoint, ensure_ascii=False),
                    "submitter": _SUBMITTER,
                    "created_by": SEEDER_ID,
                },
            )

            print(f"    ✓ {name} v{version} ({task_type})")

        print("")
        print("    ════════════════════════════════════════════════════════════")
        print(f"    ✅ Seeded {len(MODELS)} rows into mm_models")
        print("    ════════════════════════════════════════════════════════════")
