# Casbin RBAC Implementation

This document describes the Casbin-based Role-Based Access Control (RBAC) implementation in the auth-service.

## Overview

The auth-service uses **Casbin** for permission enforcement, with policies stored in the **database** (PostgreSQL) rather than static files. This makes the system:
- **Dynamic**: Permissions can be changed without code changes
- **Tenant-ready**: Uses Casbin's domain feature for multi-tenancy (currently using "default" tenant)
- **Database-driven**: All role-permission mappings come from `roles`, `permissions`, and `role_permissions` tables

## Architecture

### Database Tables

1. **`roles`**: Defines roles (ADMIN, MODERATOR, USER, GUEST)
2. **`permissions`**: Defines permissions with `resource` and `action` (e.g., "users.read", "configs.create")
3. **`role_permissions`**: Maps roles to permissions (many-to-many)
4. **`user_roles`**: Maps users to roles (many-to-many)

### Casbin Model

The Casbin model (`casbin_model.conf`) uses **RBAC with domains**:
- **Request**: `(subject, domain, object, action)`
- **Policy**: `(subject, domain, object, action)`
- **Role**: `(user, role, domain)`

This allows future multi-tenant support where each tenant is a "domain".

## Permission Matrix

The following roles and permissions are seeded into the database:

### ADMIN
- Full access to all resources: users, configs, metrics, alerts, dashboards, services, models, apiKey, roles
- All actions: create, read, update, delete, assign, remove, export

### MODERATOR
- Read and update access to users, configs, metrics, alerts, dashboards
- Read access to services, models, apiKey, roles

### USER
- Read-only access to: users, configs, metrics, alerts, dashboards, services, models

### GUEST
- Read-only access to: dashboards, metrics

## Usage

### 1. Seed the Database

First, populate the database with roles and permissions:

```bash
cd services/auth-service
python seed_roles_permissions.py
```

This script:
- Creates roles (ADMIN, MODERATOR, USER, GUEST) if they don't exist
- Creates permissions (e.g., "users.read", "configs.create") if they don't exist
- Links roles to permissions via `role_permissions` table

### 2. Service Startup

On startup, the auth-service automatically:
1. Connects to the database
2. Loads all role-permission policies into Casbin enforcer
3. Loads all user-role mappings into Casbin enforcer

This happens in `main.py` startup event via `load_policies_from_db()`.

### 3. Permission Checks

#### Check Role Permissions

```python
from casbin_enforcer import check_roles_permission

# Check if ADMIN or MODERATOR can read users
allowed = await check_roles_permission(
    roles=["ADMIN", "MODERATOR"],
    obj="users",
    act="read",
    tenant="default"
)
```

#### Check User Permissions

```python
from casbin_enforcer import check_user_permission

# Check if user_id=1 can create configs
allowed = await check_user_permission(
    user_id=1,
    obj="configs",
    act="create",
    tenant="default"
)
```

#### Check API Key Permissions

```python
from casbin_enforcer import check_apikey_permission

# Check if API key has permission for asr.inference
allowed = await check_apikey_permission(
    api_key_id=123,
    permissions=["asr.inference", "nmt.read"],  # From API key record
    obj="asr",
    act="inference",
    tenant="default"
)
```

## Reloading Policies

Currently, policies are loaded once at startup. To reload policies after changes:

1. **Restart the service** (policies reload on startup)
2. **Add an admin endpoint** to reload policies (future enhancement)

Example reload endpoint (future):
```python
@app.post("/api/v1/auth/admin/reload-policies")
async def reload_policies(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    await load_policies_from_db(db)
    return {"message": "Policies reloaded"}
```

## Adding New Permissions

To add new permissions:

1. **Insert into database**:
   ```sql
   INSERT INTO permissions (name, resource, action) 
   VALUES ('newfeature.create', 'newfeature', 'create');
   ```

2. **Assign to roles**:
   ```sql
   INSERT INTO role_permissions (role_id, permission_id)
   SELECT r.id, p.id
   FROM roles r, permissions p
   WHERE r.name = 'ADMIN' AND p.name = 'newfeature.create';
   ```

3. **Restart service** (or call reload endpoint if implemented)

## Tenant Support (Future)

The system is tenant-ready. To enable multi-tenancy:

1. Add `tenant_id` column to `user_roles` table
2. Modify `load_policies_from_db()` to load per-tenant
3. Pass actual tenant ID instead of "default" in permission checks

## Files

- `casbin_model.conf`: Casbin RBAC model definition
- `casbin_enforcer.py`: Casbin enforcer functions and DB loading
- `seed_roles_permissions.py`: Database seeding script
- `main.py`: Startup event that loads policies from DB

