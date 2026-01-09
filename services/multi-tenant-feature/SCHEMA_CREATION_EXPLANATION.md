# Schema Creation Explanation

## How Tables Are Created in Different Schemas

### Database Structure

```
multi_tenant_db (database)
├── public (schema) - Default schema
│   ├── tenants (table) - TenantDBBase
│   ├── tenant_billing_records (table) - TenantDBBase
│   ├── tenant_audit_logs (table) - TenantDBBase
│   └── ... (other tenant management tables)
│
└── tenant_acme_corp_5d448a (schema) - Tenant-specific schema
    ├── nmt_requests (table) - ServiceSchemaBase
    ├── nmt_results (table) - ServiceSchemaBase
    ├── tts_requests (table) - ServiceSchemaBase
    └── ... (all service tables)
```

### Key Differences

#### 1. TenantDBBase Tables (Public Schema)

**Location**: `db_connection.py` → `create_tables()` function

```python
# In db_connection.py
async def create_tables():
    # Creates tables in PUBLIC schema (default)
    await conn.run_sync(TenantDBBase.metadata.create_all)
```

**Behavior**:
- ✅ Creates tables in **public schema** (default)
- ✅ Called once at application startup
- ✅ Tables: `tenants`, `tenant_billing_records`, `tenant_audit_logs`, etc.
- ✅ Shared across all tenants (tenant management data)

#### 2. ServiceSchemaBase Tables (Tenant Schemas)

**Location**: `tenant_service.py` → `provision_tenant_schema()` function

```python
# In tenant_service.py
async def provision_tenant_schema(schema_name: str):
    # 1. Create the schema
    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
    
    # 2. Create tables IN THE TENANT SCHEMA
    await db.run_sync(
        lambda sync_conn: ServiceSchemaBase.metadata.create_all(
            sync_conn, 
            schema=schema_name  # ← THIS IS THE KEY!
        )
    )
```

**Behavior**:
- ✅ Creates tables in **tenant-specific schema** (e.g., `tenant_acme_corp_5d448a`)
- ✅ Called once per tenant when tenant is activated
- ✅ Tables: `nmt_requests`, `nmt_results`, `tts_requests`, etc.
- ✅ Isolated per tenant (each tenant has their own copy)

### The Critical Parameter: `schema=schema_name`

**Without `schema` parameter:**
```python
ServiceSchemaBase.metadata.create_all(sync_conn)
# ❌ Creates tables in PUBLIC schema (wrong!)
```

**With `schema` parameter:**
```python
ServiceSchemaBase.metadata.create_all(sync_conn, schema=schema_name)
# ✅ Creates tables in TENANT schema (correct!)
```

### Verification

The `provision_tenant_schema()` function now includes verification:

1. **Checks tables exist in tenant schema:**
   ```sql
   SELECT table_name 
   FROM information_schema.tables 
   WHERE table_schema = 'tenant_acme_corp_5d448a'
   ```

2. **Verifies tables are NOT in public schema:**
   ```sql
   SELECT table_name 
   FROM information_schema.tables 
   WHERE table_schema = 'public' 
   AND table_name = 'nmt_requests'  -- Should return 0 rows
   ```

### Summary Table

| Aspect | TenantDBBase | ServiceSchemaBase |
|--------|--------------|-------------------|
| **Base Location** | `db_connection.py` | `db_connection.py` |
| **Models Location** | `models/db_models.py` | `models/service_schema_models.py` |
| **Creation Function** | `create_tables()` | `provision_tenant_schema()` |
| **Schema** | `public` (default) | `tenant_<tenant_id>` (explicit) |
| **When Created** | App startup | Tenant activation |
| **How Many Copies** | 1 (shared) | 1 per tenant |
| **Purpose** | Tenant management | Service request/result data |

### How to Verify Tables Are in Correct Schema

After running `provision_tenant_schema()`, you can verify:

```sql
-- Connect to multi_tenant_db
\c multi_tenant_db

-- List all schemas
\dn

-- List tables in tenant schema
\dt tenant_acme_corp_5d448a.*

-- List tables in public schema (should NOT have service tables)
\dt public.*

-- Verify a specific table exists in tenant schema
SELECT table_schema, table_name 
FROM information_schema.tables 
WHERE table_name = 'nmt_requests';
-- Should return: tenant_acme_corp_5d448a | nmt_requests
-- Should NOT return: public | nmt_requests
```

### Important Notes

1. **Same Database, Different Schemas**: Both `TenantDBBase` and `ServiceSchemaBase` tables are in `multi_tenant_db`, but in different schemas.

2. **Same Engine**: Both use `tenant_db_engine` from `db_connection.py` - the schema is specified at table creation time.

3. **Isolation**: Each tenant's service tables are completely isolated in their own schema. Tenant A cannot see Tenant B's data.

4. **Metadata Separation**: `TenantDBBase.metadata` and `ServiceSchemaBase.metadata` are separate, so they don't interfere with each other.

