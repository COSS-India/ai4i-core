"""seed_ppu_billing_defaults

Seeds default PPU (pay-per-use) test data so billing/quota can be exercised
end-to-end for every NLP inference type, not just LLM:

  - 3 tiers in ppu_tiers: Starter, Professional, Enterprise
  - Per-inference-type monthly quotas for each tier in ppu_tier_quotas,
    covering all 13 inference_name values from
    libs/ai4i_core/ai4i_core/ppu/inference_types.yaml
  - Billing cost fields (billing_unit_type, cost_per_unit, unit_size,
    unit_rate) plus tier_ids on every mm_services row seeded by
    d3e850228f7e_seed_default_data.py, so every published NLP service has a
    resolvable price and belongs to all 3 tiers
  - The default tenant ("default organisation", seeded in the separate
    ai4iplatform_auth DB by 2362774ac241_seed_default_data.py) assigned to
    the top (Enterprise) tier in ppu_tenant_tier_assignments, with a wallet
    balance
  - A zero-usage ppu_quota_usage row per inference type for the current
    billing month, snapshotting the Enterprise quota, so usage can be
    watched incrementing during manual/automated PPU tests

Note: ppu_tenant_tier_assignments.tenant_id is a plain string with no FK —
tenants live in a different database (ai4iplatform_auth). The default
tenant's numeric id can't be looked up cross-database from this migration,
so it's taken from the DEFAULT_TENANT_ID env var (falls back to "1", the id
the default-organisation tenant normally gets as the first row in a fresh
`tenants` table — override via env if that assumption doesn't hold).

Note: "pii" has no mm_services row (PII redaction isn't a Triton-backed
service — see pii_* tables from b9e3f1a2c4d5_add_pii_tables_to_core_db.py),
so it gets a quota entry here but no billing_unit_type/cost_per_unit row to
update.

Revision ID: e5f6a7b8c9d1
Revises: b3c4d5e6f7a8
Create Date: 2026-07-06 00:00:00.000000

"""
import os
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d1'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def _generate_uuid(*parts: str) -> str:
    raw = ":".join(p.strip().lower() for p in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


# Tier definitions, lowest to highest. "top" marks the tier the default
# tenant (admin / default organisation) is assigned to.
TIERS = [
    {"key": "starter", "name": "Starter", "description": "Entry-level tier with the lowest monthly quotas."},
    {"key": "professional", "name": "Professional", "description": "Mid-tier with higher monthly quotas."},
    {"key": "enterprise", "name": "Enterprise", "description": "Top tier — highest monthly quotas. Default tier for the default organisation/admin tenant."},
]
TOP_TIER_KEY = "enterprise"

# billing_unit_type / cost_per_unit / unit_size per inference_name, matching
# libs/ai4i_core/ai4i_core/ppu/inference_types.yaml. cost_per_unit is ₹ per
# unit_size raw units (unit_rate = cost_per_unit / unit_size is derived below).
PRICING = {
    "llm":                   {"cost_per_unit": 50,   "unit_size": 1_000_000},  # ₹50 / 1M tokens
    "asr":                   {"cost_per_unit": 3,    "unit_size": 60},         # ₹3 / minute (raw unit: second)
    "nmt":                   {"cost_per_unit": 10,   "unit_size": 1_000},      # ₹10 / 1K characters
    "tts":                   {"cost_per_unit": 8,    "unit_size": 1_000},
    "ner":                   {"cost_per_unit": 5,    "unit_size": 1_000},
    "ocr":                   {"cost_per_unit": 12,   "unit_size": 1_000},
    "transliteration":       {"cost_per_unit": 5,    "unit_size": 1_000},
    "language-detection":    {"cost_per_unit": 3,    "unit_size": 1_000},
    "language-diarization":  {"cost_per_unit": 2,    "unit_size": 60},
    "speaker-diarization":   {"cost_per_unit": 2,    "unit_size": 60},
    "audio-lang-detection":  {"cost_per_unit": 1.5,  "unit_size": 60},
    "pipeline":              {"cost_per_unit": 2,    "unit_size": 1},          # ₹2 / request
    "pii":                   {"cost_per_unit": 5,    "unit_size": 1_000},      # no mm_services row — quota only
}

# mm_services.name -> inference_name, for every service seeded by
# d3e850228f7e_seed_default_data.py.
SERVICE_TASK_TYPES = {
    "indiclid-gpu": "language-detection",
    "ald-gpu": "audio-lang-detection",
    "surya-ocr-gpu": "ocr",
    "ner-gpu": "ner",
    "sd-gpu": "speaker-diarization",
    "lang-diarization-gpu": "language-diarization",
    "indic-xlit-cpu": "transliteration",
    "asr-gpu": "asr",
    "indo-aryan-tts-gpu": "tts",
    "indictrans-gpu-t4": "nmt",
    "llm-indic-prod": "llm",
}

# Monthly quota per (tier_key, inference_name), in the inference type's raw
# billing unit (tokens / seconds-as-minutes / characters / requests).
MONTHLY_QUOTAS = {
    "starter": {
        "llm": 100_000, "asr": 60, "nmt": 50_000, "tts": 50_000, "ner": 50_000,
        "ocr": 50_000, "transliteration": 50_000, "language-detection": 50_000,
        "language-diarization": 60, "speaker-diarization": 60,
        "audio-lang-detection": 60, "pipeline": 100, "pii": 50_000,
    },
    "professional": {
        "llm": 3_000_000, "asr": 300, "nmt": 2_000_000, "tts": 2_000_000, "ner": 2_000_000,
        "ocr": 2_000_000, "transliteration": 2_000_000, "language-detection": 2_000_000,
        "language-diarization": 300, "speaker-diarization": 300,
        "audio-lang-detection": 300, "pipeline": 5_000, "pii": 2_000_000,
    },
    "enterprise": {
        "llm": 50_000_000, "asr": 5_000, "nmt": 30_000_000, "tts": 30_000_000, "ner": 30_000_000,
        "ocr": 30_000_000, "transliteration": 30_000_000, "language-detection": 30_000_000,
        "language-diarization": 5_000, "speaker-diarization": 5_000,
        "audio-lang-detection": 5_000, "pipeline": 100_000, "pii": 30_000_000,
    },
}

DEFAULT_WALLET_BALANCE = "100000.00000000"


def upgrade() -> None:
    conn = op.get_bind()

    tier_ids: dict[str, str] = {t["key"]: _generate_uuid("ppu_tier", t["key"]) for t in TIERS}

    # --- 1. Tiers ---------------------------------------------------------
    for t in TIERS:
        conn.execute(
            sa.text("""
                INSERT INTO ppu_tiers (id, name, description, is_active, created_by)
                VALUES (:id, :name, :description, true, :created_by)
                ON CONFLICT (name) DO UPDATE SET
                    description = :description,
                    is_active   = true,
                    updated_at  = CURRENT_TIMESTAMP
            """),
            {
                "id": tier_ids[t["key"]],
                "name": t["name"],
                "description": t["description"],
                "created_by": SEEDER_ID,
            },
        )

    # --- 2. Per-tier, per-inference-type monthly quotas --------------------
    for tier_key, quotas in MONTHLY_QUOTAS.items():
        for inference_name, monthly_quota in quotas.items():
            conn.execute(
                sa.text("""
                    INSERT INTO ppu_tier_quotas (id, tier_id, inference_name, monthly_quota, created_by)
                    VALUES (:id, :tier_id, :inference_name, :monthly_quota, :created_by)
                    ON CONFLICT (tier_id, inference_name) DO UPDATE SET
                        monthly_quota = :monthly_quota,
                        updated_at    = CURRENT_TIMESTAMP
                """),
                {
                    "id": _generate_uuid("ppu_tier_quota", tier_key, inference_name),
                    "tier_id": tier_ids[tier_key],
                    "inference_name": inference_name,
                    "monthly_quota": monthly_quota,
                    "created_by": SEEDER_ID,
                },
            )

    # --- 3. Billing cost details + tier mapping on every seeded service ----
    all_tier_ids_literal = "{" + ",".join(f'"{tid}"' for tid in tier_ids.values()) + "}"
    for service_name, inference_name in SERVICE_TASK_TYPES.items():
        pricing = PRICING[inference_name]
        unit_rate = pricing["cost_per_unit"] / pricing["unit_size"]
        conn.execute(
            sa.text("""
                UPDATE mm_services SET
                    billing_unit_type = :inference_name,
                    cost_per_unit     = :cost_per_unit,
                    unit_size         = :unit_size,
                    unit_rate         = :unit_rate,
                    tier_ids          = CAST(:tier_ids AS text[]),
                    updated_at        = CURRENT_TIMESTAMP
                WHERE name = :service_name
            """),
            {
                "inference_name": inference_name,
                "cost_per_unit": pricing["cost_per_unit"],
                "unit_size": pricing["unit_size"],
                "unit_rate": unit_rate,
                "tier_ids": all_tier_ids_literal,
                "service_name": service_name,
            },
        )

    # --- 4. Default tenant -> top tier, with a wallet ----------------------
    default_tenant_id = (os.getenv("DEFAULT_TENANT_ID") or "1").strip()
    top_tier_id = tier_ids[TOP_TIER_KEY]
    assignment_id = _generate_uuid("ppu_tenant_tier_assignment", default_tenant_id)

    conn.execute(
        sa.text("""
            INSERT INTO ppu_tenant_tier_assignments (
                id, tenant_id, tier_id, budget_limit, available_balance,
                effective_from, effective_to, created_by
            ) VALUES (
                :id, :tenant_id, :tier_id, :budget_limit, :available_balance,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '100 years', :created_by
            )
            ON CONFLICT (id) DO UPDATE SET
                tier_id           = :tier_id,
                budget_limit      = :budget_limit,
                available_balance = :available_balance,
                effective_from    = CURRENT_TIMESTAMP,
                effective_to      = CURRENT_TIMESTAMP + INTERVAL '100 years',
                updated_at        = CURRENT_TIMESTAMP
        """),
        {
            "id": assignment_id,
            "tenant_id": default_tenant_id,
            "tier_id": top_tier_id,
            "budget_limit": DEFAULT_WALLET_BALANCE,
            "available_balance": DEFAULT_WALLET_BALANCE,
            "created_by": SEEDER_ID,
        },
    )

    # --- 5. Zero-usage quota_usage rows for the current billing month -------
    top_tier_quotas = MONTHLY_QUOTAS[TOP_TIER_KEY]
    for inference_name, monthly_quota in top_tier_quotas.items():
        conn.execute(
            sa.text("""
                INSERT INTO ppu_quota_usage (
                    id, tenant_id, inference_name, billing_month,
                    monthly_quota_snap, units_used, created_by
                ) VALUES (
                    :id, :tenant_id, :inference_name, to_char(CURRENT_TIMESTAMP, 'YYYY-MM'),
                    :monthly_quota_snap, 0, :created_by
                )
                ON CONFLICT (tenant_id, inference_name, billing_month) DO UPDATE SET
                    monthly_quota_snap = :monthly_quota_snap,
                    updated_at         = CURRENT_TIMESTAMP
            """),
            {
                "id": _generate_uuid("ppu_quota_usage", default_tenant_id, inference_name),
                "tenant_id": default_tenant_id,
                "inference_name": inference_name,
                "monthly_quota_snap": monthly_quota,
                "created_by": SEEDER_ID,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    default_tenant_id = (os.getenv("DEFAULT_TENANT_ID") or "1").strip()

    conn.execute(
        sa.text("DELETE FROM ppu_quota_usage WHERE tenant_id = :tenant_id AND created_by = :sid"),
        {"tenant_id": default_tenant_id, "sid": SEEDER_ID},
    )
    conn.execute(
        sa.text("DELETE FROM ppu_tenant_tier_assignments WHERE tenant_id = :tenant_id AND created_by = :sid"),
        {"tenant_id": default_tenant_id, "sid": SEEDER_ID},
    )

    conn.execute(
        sa.text("""
            UPDATE mm_services SET
                billing_unit_type = NULL,
                cost_per_unit     = NULL,
                unit_size         = NULL,
                unit_rate         = NULL,
                tier_ids          = NULL,
                updated_at        = CURRENT_TIMESTAMP
            WHERE name = ANY(:service_names)
        """),
        {"service_names": list(SERVICE_TASK_TYPES.keys())},
    )

    conn.execute(sa.text("DELETE FROM ppu_tier_quotas WHERE created_by = :sid"), {"sid": SEEDER_ID})
    conn.execute(sa.text("DELETE FROM ppu_tiers WHERE created_by = :sid"), {"sid": SEEDER_ID})
