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

Two modes, on `PATCH .../budget` and `PUT /auth/allocations` (Section 4.4):

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
5. Commit every row that actually changed — including any grandchildren re-fitted in step 3d, in the same transaction; push new ceilings to budget_usage
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
    "budget_effective_to": "2027-08-31"      // string (date), null if not set — NEW
  }
}
```

**Errors:** `409 ORGANISATION_ALREADY_EXISTS` (existing), `422 INVALID_BUDGET` (new — negative `allocated_budget`)

**No separate GET.** Budget fields are ordinary columns on `tenants`, so the existing `GET /auth/tenants/{tenant_id}` already returns them — `allocated_budget`, `tier_id`, `budget_effective_from/to` — alongside the identity fields.

#### `PATCH /auth/tenants/{tenant_id}/budget`

**Request**
```json
{
  "allocated_budget": 60000.00,            // number, required — new root ₹ total
  "budget_effective_from": "2026-01-01",   // string (date), optional
  "budget_effective_to": "2026-12-31",     // string (date), optional
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
    "created_at": "2026-08-26T09:00:00Z"    // string (datetime)
  }
}
```

**Errors:** `404 NOT_FOUND` (tenant), `409 APPLICATION_NAME_ALREADY_EXISTS`, `422 ALLOCATION_TOTAL_EXCEEDED`, `422 PERCENTAGE_AMOUNT_MISMATCH` (both fields given, disagree)

#### `GET /auth/tenants/{tenant_id}/applications` (the general list Applications endpoint)

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
        "allocated_budget": 50000.00        // number — derived
      }
    ]
  }
}
```

**Bulk edit for Applications** is no longer its own endpoint — merged with the Key-level bulk edit into one `PUT /auth/allocations` (Section 4.4).

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
    "created_by": "e2c9a4d1-...",          // string (uuid) — NEW, audit only; replaces the removed user_id field
    "created_at": "2026-08-26T09:00:00Z"   // string (datetime) — existing field
  }
}
```

**Errors:** `404 NOT_FOUND` (application), `422 ALLOCATION_TOTAL_EXCEEDED`, `422 PERCENTAGE_AMOUNT_MISMATCH` (both fields given, disagree)

#### `GET /auth/applications/{application_id}/api-keys` (the general admin-scoped list Keys endpoint)


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
        "allocated_budget": 24000.00           // number — derived
      }
    ]
  }
}
```

**Bulk edit for Keys** is no longer its own endpoint — merged with the Application-level bulk edit into one `PUT /auth/allocations`, below.

---

### 4.4 Bulk Allocation Edit (merged)

`PUT /auth/allocations` replaces both `PUT .../application-allocations` and `PUT .../key-allocations` — one endpoint, scoped by exactly one of two mutually-exclusive query params. New validation surface accepted deliberately in exchange for one endpoint instead of two, since the underlying validator was already shared code either way.

**Scope (query params — exactly one required):**

| Param | Scopes to | Rows must contain |
|---|---|---|
| `tenant_id` | Edge 1: Tenant → Applications | `application_id` |
| `application_id` | Edge 2: Application → Keys | `api_key_id` |

Accepts a **partial** list either way — only the rows you include are changed. Unlisted rows are read live and left exactly as they are; to remove an allocation, submit it explicitly with `allocated_percentage: 0`.

**Request** (scoped by `tenant_id` — editing Applications)
```
PUT /auth/allocations?tenant_id=101
```
```json
{
  "allocations": [
    {
      "application_id": "3fa8b8b0-...",  // required in this scope — api_key_id must be absent from every row
      "allocated_percentage": 40.0,      // number — exactly one of these two
      "allocated_budget": 40000.00       // number — exactly one of these two
    }
  ],
  "redistribution_mode": "directed",   // string, optional — governs the mandatory cascade into any changed Application's own Keys (Section 2b)
  "key_overrides": [                   // array, optional — ONLY meaningful in this scope; must be omitted/empty when scoped by application_id (Keys have no children)
    {
      "api_key_id": 4821,              // integer, required — the server resolves which Application owns it
      "allocated_percentage": 75.0,    // number — exactly one of these two
      "allocated_budget": 30000.00     // number — exactly one of these two
    }
    // key_overrides can hold entries for as many Keys as needed, even spread across several
    // of the Applications being changed in this same call
  ]
}
```

**Request** (scoped by `application_id` — editing Keys)
```
PUT /auth/allocations?application_id=3fa8b8b0-...
```
```json
{
  "allocations": [
    {
      "api_key_id": 4821,              // required in this scope — application_id must be absent from every row
      "allocated_percentage": 50.0,    // number — exactly one of these two
      "allocated_budget": 20000.00     // number — exactly one of these two
    }
  ],
  "redistribution_mode": "proportional"   // string, optional — Keys have no children, so this only affects how unlisted rows react, never a further cascade
}
```

**Response — 200 OK**
```json
{
  "success": true,
  "data": {
    "scope": "applications",              // "applications" | "keys" — echoes which edge this call resolved
    "parent_id": "101",                   // the tenant_id or application_id that scoped this call
    "total_allocated_percentage": 80.0,   // number
    "allocations": [
      {
        "application_id": "3fa8b8b0-...",   // or "api_key_id", matching scope
        "allocated_percentage": 40.0,       // number
        "allocated_budget": 40000.00        // number — recomputed
      }
    ]
  }
}
```

**New errors (on top of the shared table in Section 8):**

| Status | Code | Meaning |
|---|---|---|
| 422 | `MISSING_SCOPE` | neither `tenant_id` nor `application_id` given |
| 422 | `AMBIGUOUS_SCOPE` | both `tenant_id` and `application_id` given |
| 422 | `ROW_SCOPE_MISMATCH` | a row's `application_id`/`api_key_id` doesn't match the endpoint's scope |
| 422 | `OVERRIDES_NOT_APPLICABLE` | `key_overrides` given while scoped by `application_id` |

---
