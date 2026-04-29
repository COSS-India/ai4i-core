"""
Default Tenant Seeder (ai4iplatform_auth)

Creates a default system tenant that the seeded admin and guest users are
mapped to. The tenant is identified by its organisation name so re-running
is idempotent even though the tenants table has no unique constraint on
organisation or email.

Schema notes:
  - tenants.id is an auto-increment Integer PK (no UUID)
  - contact_name column has been renamed to name

Environment variables (all optional — defaults shown):
  DEFAULT_TENANT_ORG      → "default organisation"
  DEFAULT_TENANT_CONTACT  → "default"
  DEFAULT_TENANT_EMAIL    → "admin@ai4inclusion.org"

Rows created by this seeder carry created_by = SEEDER_ID so they can be
distinguished from user-created records.

Runs after auth_service_roles_seeder.py and before user seeders
(filename order: auth_service_r... < auth_service_t... < auth_service_y/z...).
"""
import os

from infrastructure.databases.core.base_seeder import BaseSeeder

# Fixed identity for all rows written by seeders — readable as "seed0000…"
SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"

DEFAULT_ORG = "default organisation"
DEFAULT_CONTACT = "default"
DEFAULT_EMAIL = "admin@ai4inclusion.org"


class AuthServiceDefaultTenantSeeder(BaseSeeder):
    """Seed default tenant for ai4iplatform_auth"""

    database = "ai4iplatform_auth"

    def run(self, adapter):
        org = (os.getenv("DEFAULT_TENANT_ORG") or DEFAULT_ORG).strip()
        contact = (os.getenv("DEFAULT_TENANT_CONTACT") or DEFAULT_CONTACT).strip()
        email = (os.getenv("DEFAULT_TENANT_EMAIL") or DEFAULT_EMAIL).strip()

        existing = adapter.fetch_one(
            "SELECT id FROM tenants WHERE organisation = :org LIMIT 1",
            {"org": org},
        )

        if existing:
            adapter.execute(
                """
                UPDATE tenants
                SET name       = :contact,
                    email      = :email,
                    status     = 'activated',
                    updated_by = :seeder_id
                WHERE organisation = :org
                """,
                {"contact": contact, "email": email, "org": org, "seeder_id": SEEDER_ID},
            )
            print(f"    ✓ Default tenant already exists — updated contact details ({org})")
        else:
            adapter.execute(
                """
                INSERT INTO tenants (name, organisation, email, status, created_by)
                VALUES (:contact, :org, :email, 'activated', :seeder_id)
                """,
                {
                    "contact": contact,
                    "org": org,
                    "email": email,
                    "seeder_id": SEEDER_ID,
                },
            )
            row = adapter.fetch_one(
                "SELECT id FROM tenants WHERE organisation = :org LIMIT 1",
                {"org": org},
            )
            tenant_id = row[0] if row else None
            print(f"    ✓ Created default tenant '{org}' (id: {tenant_id})")
