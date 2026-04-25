"""
Default Tenant Seeder (ai4iplatform_auth)

Creates a default system tenant that the seeded admin and guest users are
mapped to. The tenant is identified by its organisation name so re-running
is idempotent even though the tenants table has no unique constraint on
organisation or email.

Environment variables (all optional — defaults shown):
  DEFAULT_TENANT_ORG      → "AI4Inclusion"
  DEFAULT_TENANT_CONTACT  → "System Administrator"
  DEFAULT_TENANT_EMAIL    → "admin@ai4inclusion.org"

Runs after auth_service_roles_seeder.py and before user seeders
(filename order: auth_service_r... < auth_service_t... < auth_service_y/z...).
"""
import os
import uuid

from infrastructure.databases.core.base_seeder import BaseSeeder


DEFAULT_ORG = "AI4Inclusion"
DEFAULT_CONTACT = "System Administrator"
DEFAULT_EMAIL = "admin@ai4inclusion.org"


class AuthServiceDefaultTenantSeeder(BaseSeeder):
    """Seed default tenant for ai4iplatform_auth"""

    database = "ai4iplatform_auth"

    def run(self, adapter):
        org = (os.getenv("DEFAULT_TENANT_ORG") or DEFAULT_ORG).strip()
        contact = (os.getenv("DEFAULT_TENANT_CONTACT") or DEFAULT_CONTACT).strip()
        email = (os.getenv("DEFAULT_TENANT_EMAIL") or DEFAULT_EMAIL).strip()

        existing = adapter.fetch_one(
            "SELECT tenant_id FROM tenants WHERE organisation = :org LIMIT 1",
            {"org": org},
        )

        if existing:
            # Update contact details in case they changed via env, but preserve tenant_id
            adapter.execute(
                """
                UPDATE tenants
                SET contact_name = :contact,
                    email        = :email,
                    status       = 'activated'
                WHERE organisation = :org
                """,
                {"contact": contact, "email": email, "org": org},
            )
            print(f"    ✓ Default tenant already exists — updated contact details ({org})")
        else:
            tenant_id = str(uuid.uuid4())
            adapter.execute(
                """
                INSERT INTO tenants (tenant_id, contact_name, organisation, email, status)
                VALUES (:tenant_id, :contact, :org, :email, 'activated')
                """,
                {
                    "tenant_id": tenant_id,
                    "contact": contact,
                    "org": org,
                    "email": email,
                },
            )
            print(f"    ✓ Created default tenant '{org}' (tenant_id: {tenant_id})")
