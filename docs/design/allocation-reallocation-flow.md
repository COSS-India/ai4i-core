# Tenant → Application → API Key: Allocation & Reallocation Design

## 1. The full hierarchy

```
Tenant (Institution)
  allocated_budget = ₹1,00,000        ← assigned / revised directly (Section 3)
        │
        │  Edge 1: Tenant → Application  (Section 4)
        ▼
  Application "A"
  allocated_percentage = 50%  →  allocated_budget = ₹50,000
        │
        │  Edge 2: Application → API Key  (Section 4)
        ▼
  Key 1: 60% → ₹30,000        Key 2: 40% → ₹20,000
```

## 2. Tenant Budget — Create & Revise

**Create** — not a separate call. Budget is set on the same `POST /auth/tenants` call that creates the Tenant itself (Section 4.1), as optional fields alongside the existing identity ones:
```
POST /auth/tenants
{ "organisation": "...", "contact_name": "...", "email": "...", "allocated_budget": 100000.00, "tier_id": "...", "budget_effective_from": "2026-09-01" }
```

**Revise** — changes the number later:
```
PATCH /auth/tenants/{tenant_id}/budget
{ "allocated_budget": 60000.00 }
```
Applications and Keys keep their **%** by default (unless overridden — Section 2b), but their **₹** is recalculated from the new Tenant total automatically. A Tenant budget revision doesn't just check this — it **re-fits** every Application and every Key underneath it, in the same call:

```
for each Application under the Tenant:
    newAppCeiling = newTenantBudget × application.allocated_percentage / 100
    for each Key under that Application:
        newKeyCeiling = newAppCeiling × key.allocated_percentage / 100
        if newKeyCeiling < what that Key has already spent → REJECT, name the Key
```

## 2b. Redistribution mode — proportional vs directed

Two modes, on `PATCH .../budget` and `PUT .../application-allocations`:

| Mode | Untouched children | Cascades to their own children? |
|---|---|---|
| `proportional` *(default)* | % fixed, ₹ moves with the parent | Always, either direction — the whole tree scales together |
| `directed` | ₹ fixed (**protected**), % recomputed | Only on a decrease (mandatory, can't strand a child's Keys); never on an increase (left for a follow-up call) |

Children explicitly listed in `overrides` get exactly what's specified, regardless of mode.

**Algorithm** (identical shape at both edges — Tenant→Application and Application→Key):

```
INPUT:  new_parent_amount
        mode              ("proportional" | "directed", default "proportional")
        overrides[]        used only when mode = "directed"
                            each = { child_id, allocated_percentage? | allocated_budget? }

1. LOCK the parent
2. FEASIBILITY — already-spent across the parent > new_parent_amount?  → reject BUDGET_OVERCOMMITTED
3. FOR EACH child under the parent:
     a. IF child is in overrides:
          resolved = convert(override, new_parent_amount)          -- explicit, wins outright
     b. ELIF mode == "proportional":
          resolved.pct = child.allocated_percentage                -- unchanged
          resolved.amt = new_parent_amount × resolved.pct / 100
     c. ELSE  (mode == "directed", not overridden):
          resolved.amt = child.allocated_budget                    -- PROTECTED, unchanged
          resolved.pct = resolved.amt / new_parent_amount × 100    -- recomputed, floats
     d. DECIDE whether to cascade into child's own children (only Applications have any — Keys are leaves):
          cascade = child has children AND ( mode == "proportional" OR resolved.amt < child's PREVIOUS amount )
          -- proportional mode always cascades, whichever direction the parent moved, because the whole
          --   tree is meant to scale together by default (Section 2b).
          -- directed mode only cascades when resolved.amt is a DECREASE from before — mandatory, for
          --   correctness — never on a directed increase, which is left for a deliberate
          --   follow-up call so the admin can choose where it lands.
          IF cascade:
              FOR EACH grandchild under child:
                  grandchild.newAmt = resolved.amt × grandchild.allocated_percentage / 100   -- always proportional, no overrides at this depth
                  IF grandchild.newAmt < grandchild's already-spent:
                      → reject ALLOCATION_BELOW_CONSUMED, name the grandchild and child together
                      -- only reachable when resolved.amt < child's previous amount — a cascade triggered
                      --   purely by growth can never fail this, so this path is unreachable on an increase.
              -- all grandchildren fit → they're part of this commit too (step 5), not a separate call
          ELSE:
              FLOOR CHECK: resolved.amt ≥ child's already-spent?  → else reject ALLOCATION_BELOW_CONSUMED, name the child
4. SIBLING CHECK: Σ resolved.amt (all children) ≤ new_parent_amount?  → else reject ALLOCATION_TOTAL_EXCEEDED
5. Commit every row whose resolved value actually changed (version += 1) — including any grandchildren re-fitted in step 3d, in the same transaction; push new ceilings to budget_usage
```

An increase can never fail the inner re-fit (step 3d) — growing a parent can only ever create more room for its children, never less. A decrease can, which is why `directed` mode still auto-re-fits a shrinking child's own children regardless of mode — protection never extends to correctness.

## 3. The Application and Key Budget - Create & Revise

Both `Tenant → Application` and `Application → Key` need the same checks

| Check | Create | Edit |
|---|---|---|
| **Sibling check** — children's % under one parent ≤ 100% | ✅ | ✅ |
| **Floor check** — new ₹ can't fall below what's already spent. A *shrinking* Application's Keys are re-fit proportionally and checked instead (Section 2b) | — | ✅ |
| **Cascading recompute** — ₹ recalculated below a changed parent | one-time calc for the new row only | `proportional`: every level, always. `directed`: only a shrinking child's own children (mandatory) |
| **Locking** — two admins can't both succeed into an invalid total | ✅ | ✅ |

For both create and edit: the resulting ₹ ceiling has to be copied into `budget_usage` (core DB) — seeded on create, updated on edit — so billing never has to reach into auth DB to check it.

## 4. API Contract


### 4.1 Tenant — Create & Budget

#### `POST /auth/tenants` (existing endpoint)

 Four budget fields are **added**: `allocated_budget`, `tier_id`, `budget_effective_from`, `budget_effective_to` — all optional, so a Tenant can still be onboarded with no budget and have one set later via `PATCH .../budget`.

**Request**
```json
{
  "contact_name": "Jane Doe",              // string, required, 2-80 chars — existing field
  "organisation": "Acme Corp",             // string, required, 2-100 chars — existing field
  "email": "jane@acme.com",                // string (email), required — existing field
  "phone_number": "+919876543210",         // string (E.164), optional — existing field
  "plan_id": "9c1e7f0a-2b6d-...",          // string (uuid), optional — existing field
  "allocated_budget": 100000.00,           // number, optional — NEW, initial root ₹ total; omit to onboard with no budget yet
  "tier_id": "3fa8b8b0-52a1-4d9a-9c1e",    // string (uuid), optional — NEW
  "budget_effective_from": "2026-09-01",   // string (date), optional — NEW
  "budget_effective_to": "2027-08-31"      // string (date), optional — NEW
}
```

**Response — 201 Created**
```json
{
  "success": true,
  "data": {
    "tenant_id": 101,                        // integer — existing field
    "contact_name": "Jane Doe",              // string — existing field
    "organisation": "Acme Corp",             // string — existing field
    "email": "jane@acme.com",                // string — existing field
    "phone_number": "+919876543210",         // string, null if not set — existing field
    "status": "ACTIVE",                      // string — existing field
    "created_at": "2026-08-26T09:00:00Z",    // string (datetime) — existing field
    "created_by": null,                      // string (uuid), null — existing field
    "updated_at": null,                      // string (datetime), null — existing field
    "updated_by": null,                      // string (uuid), null — existing field
    "allocated_budget": 100000.00,           // number, null if not set — NEW
    "tier_id": "3fa8b8b0-52a1-4d9a-9c1e",    // string (uuid), null if not set — NEW
    "budget_effective_from": "2026-09-01",   // string (date), null if not set — NEW
    "budget_effective_to": "2027-08-31",     // string (date), null if not set — NEW
    "version": 1                             // integer — NEW, pass back as expected_version on the first PATCH .../budget
  }
}
```

**Errors:** `409 ORGANISATION_ALREADY_EXISTS` (existing), `422 INVALID_BUDGET` (new — negative `allocated_budget`)

#### `GET /auth/tenants/{tenant_id}/budget`

**Response — 200 OK**
```json
{
  "success": true,
  "data": {
    "tenant_id": 101,                        // integer
    "allocated_budget": 100000.00,           // number — the root ₹ total
    "tier_id": "3fa8b8b0-52a1-4d9a-9c1e",    // string (uuid)
    "budget_effective_from": "2026-01-01",   // string (date)
    "budget_effective_to": "2026-12-31",     // string (date)
    "version": 3                             // integer — pass back as expected_version on the next PATCH
  }
}
```

#### `PATCH /auth/tenants/{tenant_id}/budget`

**Request**
```json
{
  "allocated_budget": 60000.00,            // number, required — new root ₹ total
  "budget_effective_from": "2026-01-01",   // string (date), optional
  "budget_effective_to": "2026-12-31",     // string (date), optional
  "expected_version": 3,                   // integer, required — must match current version
  "redistribution_mode": "directed",       // string, optional — "proportional" (default) | "directed" (Section 2b)
  "application_overrides": [               // array, optional — used only when mode = "directed"
    {
      "application_id": "3fa8b8b0-...",    // string (uuid), required
      "allocated_percentage": 58.33,       // number — exactly one of these two
      "allocated_budget": 70000.00         // number — exactly one of these two
    }
  ]
}
```

**Response — 200 OK**
```json
{
  "success": true,
  "data": {
    "tenant_id": 101,                 // integer
    "allocated_budget": 60000.00,     // number
    "version": 4,                     // integer — incremented
    "applications_recomputed": 3,     // integer — count of Applications whose ₹ changed as a result
    "keys_recomputed": 7              // integer — count of Keys whose ₹ changed as a result
  }
}
```

---

### 4.2 Applications — Create & Allocations (Tenant → Application)

#### `POST /auth/tenants/{tenant_id}/applications`

Creates one Application, with an optional initial share of the Tenant's budget.

**Request**
```json
{
  "name": "Marketing Bot",           // string, required — unique per tenant, case-insensitive
  "domain": "marketing",             // string, optional
  "allocated_percentage": 30.0,      // number, optional — exactly one of these two; omit both for no ceiling
  "allocated_budget": 30000.00       // number, optional — exactly one of these two
}
```

**Response — 201 Created**
```json
{
  "success": true,
  "data": {
    "application_id": "3fa8b8b0-...",       // string (uuid)
    "tenant_id": 101,                       // integer
    "name": "Marketing Bot",                // string
    "domain": "marketing",                  // string, null if not set
    "allocated_percentage": 30.0,           // number, null if not set
    "allocated_budget": 30000.00,           // number, derived — null if allocated_percentage is null
    "status": "ACTIVE",                     // string
    "version": 1,                           // integer
    "created_at": "2026-08-26T09:00:00Z"    // string (datetime)
  }
}
```

**Errors:** `404 NOT_FOUND` (tenant), `409 APPLICATION_NAME_ALREADY_EXISTS`, `422 ALLOCATION_TOTAL_EXCEEDED`, `422 PERCENTAGE_AMOUNT_MISMATCH` (both fields given, disagree)

#### `GET /auth/tenants/{tenant_id}/application-allocations`

**Response — 200 OK**
```json
{
  "success": true,
  "data": {
    "tenant_id": 101,                       // integer
    "tenant_allocated_budget": 100000.00,   // number — the total being sliced
    "total_allocated_percentage": 80.0,     // number — sum across all Applications below
    "applications": [
      {
        "application_id": "3fa8b8b0-...",   // string (uuid)
        "name": "Marketing Bot",            // string
        "allocated_percentage": 50.0,       // number
        "allocated_budget": 50000.00,       // number — derived
        "version": 2                        // integer — pass back per-row on the next PUT
      }
    ]
  }
}
```

#### `PUT /auth/tenants/{tenant_id}/application-allocations`

Accepts a **partial** list — only the Applications you include are changed. Unlisted Applications are read live from the database and left exactly as they are; they are never zeroed by omission. To remove an allocation, submit it explicitly with `allocated_percentage: 0`.

**Request**
```json
{
  "allocations": [
    {
      "application_id": "3fa8b8b0-...",  // string (uuid), required
      "allocated_percentage": 40.0,      // number — exactly one of these two
      "allocated_budget": 40000.00,      // number — exactly one of these two
      "expected_version": 2              // integer, required — must match this Application's current version
    }
    // list only the Applications you're changing — anything left out is untouched
    // to remove an allocation, send it explicitly with allocated_percentage: 0
  ],
  "redistribution_mode": "directed",   // string, optional — governs the mandatory cascade into any changed Application's own Keys (Section 2b)
  "key_overrides": [                   // array, optional — flat, like application_overrides, keyed by api_key_id instead
    {
      "api_key_id": 4821,              // integer, required — the server resolves which Application owns it
      "allocated_percentage": 75.0,    // number — exactly one of these two
      "allocated_budget": 30000.00     // number — exactly one of these two
    }
    // any Key NOT listed here follows the normal per-mode cascade (proportional re-fit, or
    // protected/re-fit-on-shrink for directed) against its own Application's new amount —
    // key_overrides can hold entries for as many Keys as needed, even spread across several
    // of the Applications being changed in this same call, exactly like application_overrides
    // does for Applications within the Tenant-level call
  ]
}
```

**Response — 200 OK**
```json
{
  "success": true,
  "data": {
    "tenant_id": 101,                     // integer
    "total_allocated_percentage": 80.0,   // number
    "allocations": [
      {
        "application_id": "3fa8b8b0-...",   // string (uuid)
        "allocated_percentage": 40.0,       // number
        "allocated_budget": 40000.00,       // number — recomputed
        "version": 3                        // integer — incremented
      }
    ]
  }
}
```

---

### 4.3 API Keys — Create & Allocations (Application → API Key)

#### `POST /auth/api-keys` (existing endpoint, extended)

Two fields are added: `application_id`  and `allocated_percentage` (new, optional).

**Request**
```json
{
  "key_name": "reporting-bot",          // string, required — existing field
  "permissions": ["nmt.inference"],     // array of string, required, min 1 — existing field
  "expires_days": 90,                   // integer, optional — existing field, defaults to API_KEY_EXPIRE_DAYS
  "application_id": "3fa8b8b0-...",     // string (uuid), required — NEW
  "allocated_percentage": 30.0,         // number, optional — NEW, exactly one of these two; omit both for an uncapped key
  "allocated_budget": 15000.00          // number, optional — NEW, exactly one of these two
}
```

**Response — 201 Created**
```json
{
  "success": true,
  "data": {
    "id": 4821,                            // integer
    "api_key": "a1b2c3d4...e5f6",          // string — 32-char hex, shown only once — existing field
    "key_name": "reporting-bot",           // string — existing field
    "permissions": ["nmt.inference"],      // array of string — existing field
    "expires_at": "2026-11-24T09:00:00Z",  // string (datetime), null if no expiry — existing field
    "application_id": "3fa8b8b0-...",      // string (uuid) — NEW
    "allocated_percentage": 30.0,          // number, null if not set — NEW
    "allocated_budget": 15000.00,          // number, derived, null if allocated_percentage is null — NEW
    "is_active": true,                     // boolean — existing field
    "version": 1,                          // integer — NEW
    "created_by": "e2c9a4d1-...",          // string (uuid) — NEW, audit only; replaces the removed user_id field
    "created_at": "2026-08-26T09:00:00Z"   // string (datetime) — existing field
  }
}
```

**Errors:** `404 NOT_FOUND` (application), `422 ALLOCATION_TOTAL_EXCEEDED`, `422 PERCENTAGE_AMOUNT_MISMATCH` (both fields given, disagree)

#### `GET /auth/applications/{application_id}/key-allocations`

**Response — 200 OK**
```json
{
  "success": true,
  "data": {
    "application_id": "3fa8b8b0-...",          // string (uuid)
    "application_allocated_budget": 40000.00,  // number — the total being sliced
    "total_allocated_percentage": 100.0,       // number — sum across all Keys below
    "keys": [
      {
        "api_key_id": 4821,                    // integer
        "key_name": "reporting-bot",           // string — matches CreateAPIKeyData's field name
        "is_active": true,                     // boolean — revoked keys still appear, still count
        "allocated_percentage": 60.0,          // number
        "allocated_budget": 24000.00,          // number — derived
        "version": 2                           // integer — pass back per-row on the next PUT
      }
    ]
  }
}
```

#### `PUT /auth/applications/{application_id}/key-allocations`

List only the Keys you're changing, unlisted Keys are read live and left alone, removal must be explicit (`allocated_percentage: 0`).

**Request**
```json
{
  "allocations": [
    {
      "api_key_id": 4821,              // integer, required
      "allocated_percentage": 50.0,    // number — exactly one of these two
      "allocated_budget": 20000.00,    // number — exactly one of these two
      "expected_version": 2            // integer, required — must match this Key's current version
    }
    // list only the Keys you're changing — anything left out is untouched
    // to remove an allocation, send it explicitly with allocated_percentage: 0
  ]
}
```

**Response — 200 OK**
```json
{
  "success": true,
  "data": {
    "application_id": "3fa8b8b0-...",     // string (uuid)
    "total_allocated_percentage": 100.0,  // number
    "allocations": [
      {
        "api_key_id": 4821,               // integer
        "allocated_percentage": 50.0,     // number
        "allocated_budget": 20000.00,     // number — recomputed
        "version": 3                      // integer — incremented
      }
    ]
  }
}
```

---
