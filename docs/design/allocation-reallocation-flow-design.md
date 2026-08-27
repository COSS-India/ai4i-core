# Tenant → Application → API Key: Allocation & Reallocation Design

## 1. The full hierarchy

The Tenant is the **root** — it doesn't get "allocated" a %, it gets **assigned a budget directly**. Everything below it is a % of that.

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

**The one rule to remember:** every ₹ ceiling below the Tenant is *derived* — `child ₹ = parent ₹ × child's %`. Which means: **change the Tenant's ₹, and every Application and every Key underneath silently changes too.** That's the part worth designing carefully, covered in Section 3.

---

## 2. What each level touches in the database

| Level | % lives here | ₹ ceiling lives here | Actual spend lives here |
|---|---|---|---|
| Tenant | — (root, assigned not allocated) | `tenants.allocated_budget` (auth DB) | rolled up from `budget_usage` (core DB) |
| Application | `applications.allocated_percentage` (auth DB) | `applications.allocated_budget` (auth DB, derived) | rolled up from `budget_usage` (core DB), via its keys |
| API Key | `api_key.allocated_percentage` (auth DB) | `api_key.allocated_budget` (auth DB, derived) | `budget_usage.api_key_budget_used` (core DB) |

Every % and every ₹ ceiling lives in **auth DB**. Only actual **spend** lives in **core DB**.

---

## 3. Tenant Budget — Create & Revise

This isn't an "allocation" (there's no parent above it) — it's a direct assignment. But it's the most powerful operation in the whole hierarchy, because it moves the number everything else is a % of.

**Create** — not a separate call. Budget is set on the same `POST /auth/tenants` call that creates the Tenant itself (Section 8.1), as optional fields alongside the existing identity ones:
```
POST /auth/tenants
{ "organisation": "...", "contact_name": "...", "email": "...", "allocated_budget": 100000.00, "tier_id": "...", "budget_effective_from": "2026-09-01" }
```
Nothing exists below the Tenant yet, so there's nothing to check — just save it.

**Revise** — changes the number later:
```
PATCH /auth/tenants/{tenant_id}/budget
{ "allocated_budget": 60000.00 }
```
This is where it gets interesting. Applications and Keys keep their **%**, but their **₹** is recalculated from the new Tenant total — automatically, without anyone touching them directly.

**Worked example — why this can silently break a child:**

```
Before:  Tenant ₹1,00,000 → App A (50%) = ₹50,000 ceiling, App A has already spent ₹40,000  ✓ fine

Admin cuts Tenant budget to ₹60,000 (App A's % stays 50%, nobody touched App A):

After:   Tenant ₹60,000  → App A (50%) = ₹30,000 ceiling  ✗  but App A already spent ₹40,000!
```

App A's own settings never changed — but it's now ₹10,000 **over** its own (recalculated) ceiling, purely as a side effect of the Tenant edit. A Tenant budget revision doesn't just check this — it **re-fits** every Application and every Key underneath it, automatically, in the same call (see Section 3b for the full mechanism and Section 4's algorithm):

```
for each Application under the Tenant:
    newAppCeiling = newTenantBudget × application.allocated_percentage / 100
    for each Key under that Application:
        newKeyCeiling = newAppCeiling × key.allocated_percentage / 100
        if newKeyCeiling < what that Key has already spent → REJECT, name the Key
```

If the re-fit can't be done without violating a Key's own spend, the whole revision is refused and the admin is told exactly which Key is the problem — same principle as the Application-vs-Key floor check, just run two levels deep instead of one.

---

## 3b. Redistribution mode — proportional vs directed

When a parent's ₹ changes, every child underneath it has to react somehow. Two modes, on `PATCH .../budget` and `PUT .../application-allocations`:

| Mode | Untouched children | Cascades to their own children? |
|---|---|---|
| `proportional` *(default)* | % fixed, ₹ moves with the parent | Always, either direction — the whole tree scales together |
| `directed` | ₹ fixed (**protected**), % recomputed | Only on a decrease (mandatory, can't strand a child's Keys); never on an increase (left for a deliberate follow-up call) |

Children explicitly listed in `overrides` get exactly what's specified, regardless of mode.

**Algorithm** (same shape at both edges — Tenant→Application and Application→Key):
```
FOR EACH child under the parent:
    resolved = override(child)  OR  proportional(child)  OR  protected(child)   -- per mode, per row above
    cascade = child has its own children AND (mode == proportional OR resolved.amt < child's old amt)
    IF cascade:
        re-fit child's own children proportionally against resolved.amt
        IF any of them < its own spent → REJECT, name it (and the child)
    ELSE:
        IF resolved.amt < child's already-spent → REJECT, name child
CHECK: Σ resolved.amt ≤ new_parent_amount → else REJECT
COMMIT every changed row (this child + any re-fitted grandchildren), push to budget_usage
```

An increase can never fail the inner re-fit — growing a parent only ever creates room. A decrease can, which is why `directed` mode always re-fits a shrinking child's own children regardless of the mode setting — protection never extends to correctness.

---

## 4. The Application and Key edges (both work identically)

Both `Tenant → Application` and `Application → Key` need the same checks — but not all of them apply the same way to **create** vs **edit**:

| Check | Create | Edit | Why |
|---|---|---|---|
| **Sibling check** — children's % under one parent ≤ 100% | ✅ | ✅ | A new child's % still has to fit alongside the existing siblings' total — same math either way. |
| **Floor check** — new ₹ can't fall below what's already spent. For a *shrinking* Application specifically, its Keys are re-fit proportionally against the new ₹ and checked instead (Section 3b) — Keys have no children, so this reduces to plain spend for them | — | ✅ | A brand-new resource has ₹0 spent and no children, so there's nothing yet to violate. |
| **Cascading recompute** — ₹ recalculated below a changed parent | one-time calc for the new row only | `proportional`: every level, always. `directed`: only a shrinking child's own children (mandatory); a growing overridden child's children are left untouched (Section 3b) | Create doesn't touch existing siblings — it computes one new row's own ₹. |
| **Locking** — two admins can't both succeed into an invalid total | ✅ | ✅ | Two admins creating siblings at once hit the exact same read-check-write race as two admins editing. |

Plus one shared plumbing step, for both create and edit: the resulting ₹ ceiling has to be copied into `budget_usage` (core DB) — seeded on create, updated on edit — so billing never has to reach into auth DB to check it.

---

## 5. The real question: one shared Allocation API, or extend the existing resource APIs?

### Option A — Add fields to the existing endpoints
Put `allocated_percentage` directly into the existing "create/edit Application" and "create/edit Key" requests (see the worked example at the top of this doc).

- ✅ Simple, matches the schema — the % literally lives on those tables already
- ❌ On its own, the 4 checks in Section 4 get built twice — once for Applications, once for Keys — and tend to drift apart over time
- **Refinement used in the recommendation below:** keep the field on **create** only (see Section 6) — it's safe there because adding one new child still goes through the same shared check as the bulk endpoint. Drop it from **edit** — that's where a per-resource change can race with a sibling's change, which is exactly what the bulk-only rule prevents.

### Option B — One fully generic Allocation API
`POST /allocations { parentType, parentId, childType, childId, percentage }` for any level, including the Tenant.

- ✅ One codebase for all the validation logic
- ❌ Doesn't match the schema (there's no generic `allocations` table — the % sits on the specific resource), so this adds a layer of abstraction without removing real complexity

### Option C — Level-specific bulk endpoints, sharing one internal validator *(recommended)*
Same shared internal function (sibling-check, floor-check, cascade, lock, core-DB sync) called from resource-scoped endpoints, one per edge.

- ✅ Matches the schema, avoids duplicated logic, URLs stay intuitive
- ✅ Naturally owned by **auth-service**, since every %, every ₹, and now the Tenant's own budget all live in auth DB
- ❌ Still three endpoints to maintain (acceptable — they're thin wrappers around one shared core)

---

## 5b. Do you actually need the bulk edit endpoint?

The lock (Section 4, point 4) is what stops two admins from corrupting the total — not the fact that an endpoint is "bulk." A locked single-item `PATCH` is fully safe for two different admins editing two different keys at once. So this is a real fork, decided by one question: **can one admin change more than one sibling's % as a single Save?**

| Admins only ever change one key's % at a time | Admins rebalance several siblings in one screen |
|---|---|
| Drop the bulk endpoint. Add the field + the same lock to the existing `PATCH` endpoints. Fewer endpoints, fully safe. | Keep the bulk endpoint. A sequence of single-item calls forces the client to shrink-before-grow to avoid a false rejection, and a failure partway through leaves a **half-applied, fully committed** rebalance visible to billing — a bulk call wraps the whole set in one transaction, so it's all-or-nothing. |

Worth confirming which UX is real before locking in either path — this changes the answer, not just the plumbing.

**This fork applies to edit only, not create.** Create's race is closed by the same lock either way, because create only ever writes **one** row — the new Application or Key itself. It never rewrites an existing sibling, so there's no multi-row rebalance to go half-applied. Bulk earns its keep specifically for "several *existing* rows change together in one Save" — a shape create never has. So regardless of which side of the table above you land on for edit, create stays a single-item endpoint with `allocated_percentage` as an optional field, protected by the same shared lock.

## 6. Recommendation: Option C, with create kept on the resource itself

**Create — % is just an optional field, same call as creating the resource:**
```
POST /auth/tenants/{tenant_id}/applications   { name, domain, allocated_percentage? }
POST /auth/api-keys                           { key_name, permissions, application_id, allocated_percentage? }
```

**Edit an existing % — always through the bulk endpoint, even for one child:**
```
PATCH /auth/tenants/{tenant_id}/budget                       ← Tenant's own budget (Section 3)
PUT   /auth/tenants/{tenant_id}/application-allocations       ← Edge 1: re-slice Applications
PUT   /auth/applications/{application_id}/key-allocations           ← Edge 2: re-slice Keys
```
A plain `PATCH /auth/applications/{id}` or `PATCH /auth/api-keys/{id}` explicitly **rejects** an `allocated_percentage` field if one is sent — `422 ALLOCATION_FIELD_NOT_ALLOWED_ON_EDIT` — rather than silently ignoring it, so a client can't accidentally believe it changed the allocation when it didn't.

Plus matching `GET`s to read current state before editing — none of them a separate "-allocations" endpoint (Section 8.1/8.2/8.3): Tenant budget is just part of `GET /auth/tenants/{tenant_id}`; Application and Key allocations are just part of their general list endpoints:
```
GET /auth/tenants/{tenant_id}
GET /auth/tenants/{tenant_id}/applications
GET /auth/applications/{application_id}/api-keys
```

**Both entry points — the create call and the bulk call — run through the exact same shared validator:**
```
POST .../applications  { allocated_percentage }  ──┐
                                                    ├──► [shared validator: lock → sibling-check → floor-check → cascade → core-DB sync]
PUT  .../application-allocations  { [...] }  ─────┘
```
Create just hands the validator a "set of one new child" instead of "replace the whole existing set" — same lock, same checks, same sync step, different caller.

All write paths share this one validator, just with a different cascade depth:
- Tenant budget revise → checks 2 levels down (Applications, then their Keys)
- Application allocations (create or bulk edit) → checks 1 level down (its Keys)
- Key allocations (create or bulk edit) → checks 0 levels down (nothing below a Key)

**Why auth-service owns all three:** every number involved — Tenant's ₹, every Application's %/₹, every Key's %/₹ — now lives directly on `tenants` / `applications` / `api_key`, all in auth DB. auth-service just needs one small hook, after any of these three writes, to push the resulting ceilings into `budget_usage` in core DB.

---

## 7. Flow — Tenant budget revision (the deepest case)

```
Admin: PATCH /auth/tenants/{tenant_id}/budget  { allocated_budget: 60000, redistribution_mode?, application_overrides? }
        │
        ▼
   [shared validator]
   1. lock this tenant
   2. for each Application → resolve via override / proportional / protected (Section 3b)
   3. cascade into that Application's Keys if mode = proportional, or if it shrank   (reject + name the Key, if any fails)
   4. save new Tenant budget (auth DB)
   5. save every changed Application ₹ and Key ₹ (auth DB)
   6. push every changed ceiling into budget_usage (core DB)
        │
        ▼
      200 OK
```

The Application-level and Key-level endpoints run the same six steps, just starting one level lower — same validator, same lock, same sync step, less cascade depth.

---

## 8. API Contract

Three resources, each with a `GET` (read current state) and a write endpoint.

**No `version` / `expected_version` field.** Not maintained — the lock (Section 4/5b) already fully guarantees the aggregate invariant (Σ% ≤ 100%, floor check) on its own, because the server re-reads siblings fresh under the lock on every write. The one thing dropping this gives up: if two admins edit the **same single row** at once, the second write silently overwrites the first with no error to either side — last-write-wins, accepted as a fine trade-off for a simpler contract.

### 8.1 Tenant — Create & Budget

#### `POST /auth/tenants` (existing endpoint, extended)

**Not a new endpoint** — this already exists (`app/routes/tenants.py`, schema `TenantCreate`/`TenantResponse`), and its identity fields are unchanged. Four budget fields are **added**: `allocated_budget`, `tier_id`, `budget_effective_from`, `budget_effective_to` — all optional, so a Tenant can still be onboarded with no budget and have one set later via `PATCH .../budget`. No lock or sibling-check runs here: a brand-new Tenant has no Applications or Keys yet, so there is nothing downstream to violate (Section 3) — this is a plain insert.

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

**No separate GET.** An earlier version of this doc argued for `GET /auth/tenants/{tenant_id}/budget` as its own endpoint, on the grounds that allocation screens don't need the full Tenant identity record alongside it — not worth a whole separate route for a handful of fields already on the same row. `allocated_budget`, `tier_id`, `budget_effective_from/to` are ordinary columns, so `GET /auth/tenants/{tenant_id}` already returns them alongside identity fields.
```

#### `PATCH /auth/tenants/{tenant_id}/budget`

**Request**
```json
{
  "allocated_budget": 60000.00,            // number, required — new root ₹ total
  "budget_effective_from": "2026-01-01",   // string (date), optional
  "budget_effective_to": "2026-12-31",     // string (date), optional
  "redistribution_mode": "directed",       // string, optional — "proportional" (default) | "directed" (Section 3b)
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

### 8.2 Applications — Create & Allocations (Tenant → Application)

#### `POST /auth/tenants/{tenant_id}/applications`

Creates one Application, with an optional initial share of the Tenant's budget. Goes through the shared validator (Section 6) as a "set of one new child" — same lock and sibling check as the bulk endpoint below.

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

**Errors:** `404 NOT_FOUND` (tenant), `409 APPLICATION_NAME_ALREADY_EXISTS`, `422 ALLOCATION_TOTAL_EXCEEDED`

#### `GET /auth/tenants/{tenant_id}/applications` (the general list Applications endpoint)

**Not a separate "-allocations" endpoint.** `allocated_percentage`/`allocated_budget` are ordinary columns on `applications`; no other endpoint currently lists Applications under a Tenant, so this is that endpoint.

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

#### `PUT /auth/tenants/{tenant_id}/application-allocations`

Accepts a **partial** list — only the Applications you include are changed. Unlisted Applications are read live from the database under the lock and left exactly as they are; they are never zeroed by omission. To remove an allocation, submit it explicitly with `allocated_percentage: 0` — omission always means "leave alone," never "delete." This is what lets the same endpoint serve both a single-Application edit and a full rebalance of every Application at once.

**Request**
```json
{
  "allocations": [
    {
      "application_id": "3fa8b8b0-...",  // string (uuid), required
      "allocated_percentage": 40.0,      // number — exactly one of these two
      "allocated_budget": 40000.00       // number — exactly one of these two
    }
    // list only the Applications you're changing — anything left out is untouched
    // to remove an allocation, send it explicitly with allocated_percentage: 0
  ],
  "redistribution_mode": "directed",   // string, optional — governs the mandatory cascade into any changed Application's own Keys (Section 3b)
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
        "allocated_budget": 40000.00        // number — recomputed
      }
    ]
  }
}
```

---

### 8.3 API Keys — Create & Allocations (Application → API Key)

#### `POST /auth/api-keys` (existing endpoint, extended)

**Not a new endpoint** — this already exists (`app/routes/api_key.py`). Two fields are added: `application_id` (new, mandatory — Section 1: every key belongs to an Application, no exceptions) and `allocated_percentage` (new, optional). Goes through the shared validator as a "set of one new child," same as an Application create. Field names and the response envelope match the real schema (`CreateAPIKeyRequest` / `CreateAPIKeyData`) — snake_case, not camelCase, and wrapped in `{"success": true, "data": ...}`.

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

**Errors:** `404 NOT_FOUND` (application), `422 ALLOCATION_TOTAL_EXCEEDED`

#### `GET /auth/applications/{application_id}/api-keys` (the general admin-scoped list Keys endpoint)

**Not a separate "-allocations" endpoint.** The existing `GET /auth/api-keys` is self-service (a caller's own keys) — "list every Key under this Application" for an admin doesn't exist yet regardless of allocations, so this is that endpoint.

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

#### `PUT /auth/applications/{application_id}/key-allocations`

Same partial-list rules as 8.2, one level down: list only the Keys you're changing, unlisted Keys are read live and left alone, removal must be explicit (`allocated_percentage: 0`).

**Request**
```json
{
  "allocations": [
    {
      "api_key_id": 4821,              // integer, required
      "allocated_percentage": 50.0,    // number — exactly one of these two
      "allocated_budget": 20000.00     // number — exactly one of these two
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
        "allocated_budget": 20000.00      // number — recomputed
      }
    ]
  }
}
```

---

### 8.4 Errors (shared across all three write endpoints)

Matches the real auth-service error envelope (`ai4i_core.exceptions.ErrorDetail`): `{"detail": {"code", "message", "timestamp", "details"}}` — not a custom shape. `details` is a plain string, so the identifying fields (which Application, which Key, the two amounts) are folded into `message` and `details` rather than returned as separate JSON fields.

| Status | Code | Meaning |
|---|---|---|
| 404 | `NOT_FOUND` | Tenant / Application / Key id doesn't exist |
| 422 | `ALLOCATION_TOTAL_EXCEEDED` | the submitted set adds up to more than 100% |
| 422 | `ALLOCATION_BELOW_CONSUMED` | a new ceiling would sit below what's already been spent |
| 409 | `BUDGET_OVERCOMMITTED` | the parent is already over its own budget (via overshoot) — fix that before re-slicing its children |
| 422 | `PERCENTAGE_AMOUNT_MISMATCH` | both `allocated_percentage` and `allocated_budget` given for the same row, and they don't agree |

**Example error body** (the richest case — a Key-level floor violation):
```json
{
  "detail": {
    "code": "ALLOCATION_BELOW_CONSUMED",   // string — machine-readable code
    "message": "Key 4821 has already consumed ₹13,200.00, which is above the requested ceiling of ₹12,500.00",
    "timestamp": 1785060000.123,           // float — unix epoch seconds
    "details": "application_id=3fa8b8b0-... api_key_id=4821 consumed_amount=13200.00 requested_budget=12500.00"
  }
}
```

---

## 9. Code Impact — Modules Affected

Three services are touched. auth-service carries almost all of it, because every % and every ₹ ceiling now lives there.

### 9.1 auth-service — owns all three write endpoints

| Module | Change |
|---|---|
| **Data models** | Tenant and API Key models gain allocation fields; new Application model added |
| **Repositories** | Tenant and API Key repositories gain allocation/sibling-sum queries; new Application repository |
| **Allocation validator** (new) | one shared module: lock → resolve (override/proportional/protected) → mode-aware cascade → sibling-check → floor-check (Section 3b) — called by every write path below |
| **Tenant module (service + API)** | budget create/revise, calling the shared validator |
| **API Key module (service + API)** | `POST /auth/api-keys` extended to accept `application_id` + `allocated_percentage` |
| **Application module (service + API)** | new — Application CRUD, application-allocation read/write, and key-allocation read/write (key-allocations route through the Application module, since the path is `/auth/applications/{id}/key-allocations`) |
| **Request/response schemas** | new/updated shapes matching Section 8 |
| **DB migration** | new `applications` table; new columns on `tenants`, `api_key` |

### 9.2 platform-core-service — receives the ceiling snapshot, holds the ledger

| Module | Change |
|---|---|
| **Data model** | new Budget Usage model — ceiling snapshot + spend |
| **Internal API** | new route to receive ceiling-snapshot pushes from auth-service |
| **Reconciliation job** (new) | periodic sweep comparing each ceiling's `updated_at` in auth against the snapshot's, re-syncing drift (no `version` column to compare instead — Section 8) |
| **DB migration** | new `budget_usage` table |

### 9.3 kafka-consumers — enforcement at billing time

| Module | Change |
|---|---|
| **Billing consumer** | reads the ceiling snapshot and spend for the enforcement check; updates spend per billed request |

### 9.4 Shared

| Module | Change |
|---|---|
| **Concurrency utility** (`libs/ai4i_core`) | advisory-lock helper, if one doesn't already exist — reused by the allocation validator |

---

## 10. Summary of Key Changes

**Database**
- New table: `applications` (auth DB)
- New table: `budget_usage` (core DB)
- New columns: `tenants.allocated_budget`, `budget_effective_from/to` (auth DB)
- New columns: `api_key.application_id`, `allocated_percentage`, `allocated_budget` (auth DB)
- Removed: `api_key.user_id` → replaced by `created_by` (audit only)

**Code**
- **auth-service:** new Application module (model, repo, service, routes); one new shared `allocation_validator` (lock → sibling-check → floor-check → cascade); `tenant_service` and `api_key_service` extended to call it
- **platform-core-service:** new `budget_usage` model; new internal route to receive ceiling snapshots; new reconciliation sweep
- **kafka-consumers:** `_billing.py` reads/updates `budget_usage` for enforcement — no other file changes
- **libs/ai4i_core:** shared advisory-lock helper, if not already present

**Behaviour**
- 3 write paths (Tenant budget, Application allocations, Key allocations) all go through the *same* shared validator — one lock, one check, one cascade depth per level
- `proportional` (default) cascades every level automatically, either direction; `directed` only auto-cascades a shrink (mandatory) — a directed increase leaves deeper levels untouched (Section 3b)
- Every allocation field accepts `allocated_percentage` **or** `allocated_budget` — server computes the other
- Create keeps allocation as plain optional fields; editing an existing % only happens via the partial-list `PUT` endpoints, never a single-item `PATCH`
- Billing enforcement reads only `budget_usage` (core DB) — never depends on auth-service being reachable

---

## 11. File-Level Changes

### 11.1 auth-service

| File | Change |
|---|---|
| `app/models/tenant.py` | add `allocated_budget`, `budget_effective_from/to` |
| `app/models/api_key.py` | add `application_id` (NOT NULL), `allocated_percentage`, `allocated_budget`; remove `user_id`, add `created_by` |
| `app/models/application.py` | **new** — the Application model |
| `app/repositories/tenant_repository.py` | add budget read/update queries |
| `app/repositories/api_key_repository.py` | add sibling-sum + allocation queries |
| `app/repositories/application_repository.py` | **new** |
| `app/services/allocation_validator.py` | **new** — the one shared function: lock → sibling-check → floor-check → cascade |
| `app/services/tenant_service.py` | add budget create/revise, calling the shared validator |
| `app/services/api_key_service.py` | `create_api_key` takes `application_id`, `allocated_percentage`; calls the shared validator |
| `app/services/application_service.py` | **new** — create/edit Application, calling the shared validator |
| `app/routes/tenants.py` | extend `GET /auth/tenants/{id}` with budget fields; add `PATCH .../budget` |
| `app/routes/api_key.py` | extend `POST /api-keys` with `application_id` (required), `allocated_percentage` (optional) |
| `app/routes/applications.py` | **new** — Application CRUD; `GET .../applications` (list, includes allocation fields) + `PUT .../application-allocations` (bulk edit); `GET .../{application_id}/api-keys` (list) + `PUT .../{application_id}/key-allocations` (bulk edit) (path lives under `/auth/applications`, not `/auth/api-keys`) |
| `app/schemas/*.py` | request/response models matching Section 8 |
| DB migration | new `applications` table; new columns on `tenants`, `api_key` |

### 11.2 platform-core-service

| File | Change |
|---|---|
| `app/models/budget_usage.py` | **new** — `api_key_budget_snap`, `api_key_budget_used` |
| `app/routes/internal.py` | add an internal route to receive ceiling-snapshot pushes from auth-service |
| `app/services/` (new module) | reconciliation sweep — compares `updated_at` (auth) vs snapshot's last-synced timestamp (core), re-syncs drift |
| DB migration | new `budget_usage` table |

### 11.3 kafka-consumers

| File | Change |
|---|---|
| `consumers/payperuse_consumer/_billing.py` | read `api_key_budget_snap` / `api_key_budget_used` from `budget_usage` for the ceiling check; update `api_key_budget_used` per billed request |

### 11.4 Shared

| File | Change |
|---|---|
| `libs/ai4i_core` | advisory-lock helper, if one doesn't already exist — reused by `allocation_validator.py` |
