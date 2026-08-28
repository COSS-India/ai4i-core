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
Applications and Keys keep their **%** by default (unless explicitly pinned via `application_overrides` — Section 2b), but their **₹** is recalculated from the new Tenant total automatically. A Tenant budget revision doesn't just check this — it **re-fits** every Application and every Key underneath it, in the same call:

```
for each Application under the Tenant:
    newAppCeiling = newTenantBudget × application.allocated_percentage / 100
    for each Key under that Application:
        newKeyCeiling = newAppCeiling × key.allocated_percentage / 100
        if newKeyCeiling < what that Key has already spent → REJECT, name the Key
```

## 2b. Unlisted children — the re-fit rule

No mode to choose. Whenever a parent's ₹ total changes — a Tenant budget revision, or a bulk
allocation edit that lists some but not all of a parent's children — the children **not** given
an explicit new value in that same call still need a defined outcome. One unconditional rule,
identical shape at both edges (Tenant→Application and Application→Key), on both increase and
decrease:

**Algorithm:**

```
INPUT:  new_parent_amount
        explicit[]   rows given directly in this call — a PATCH .../budget's application_overrides
                     (and their own nested api_key_allocations), or a PUT /auth/allocations row
                     (application_allocations / api_key_allocations, nested per Section 4.4)
                     each = { child_id, allocated_percentage? | allocated_budget? }

1. LOCK the parent
2. FEASIBILITY — already-spent across the parent > new_parent_amount?  → reject BUDGET_OVERCOMMITTED
3. RESOLVE every EXPLICIT child to its stated value:
     resolved = convert(explicit_row, new_parent_amount)
     FLOOR CHECK: resolved.amt ≥ child's already-spent?  → else reject ALLOCATION_BELOW_CONSUMED, name the child
4. room_remaining = new_parent_amount − Σ resolved.amt (all explicit children)
5. unlisted_old_total = Σ old ₹ (all children NOT in explicit[])
6. FOR EACH unlisted child:
     resolved.amt = room_remaining × (child's old ₹ / unlisted_old_total)   -- its share of what's
                                                                             -- left, weighted by its
                                                                             -- own size among the
                                                                             -- other unlisted siblings
     resolved.pct = resolved.amt / new_parent_amount × 100                 -- recomputed, floats
     FLOOR CHECK: resolved.amt ≥ child's already-spent?  → else reject ALLOCATION_BELOW_CONSUMED, name the child
     -- unconditional — this runs whether the parent grew or shrank. When EVERY child is unlisted
     --   (e.g. PATCH .../budget, which only ever supplies one number, never per-child rows), this
     --   reduces to the simple case: each child's own percentage applied directly to
     --   new_parent_amount, because unlisted_old_total then equals the parent's own old total.
7. FOR EACH child whose resolved.amt actually changed (explicit or re-fit) AND has children of its
   own (only Applications do — Keys are leaves):
     -- cascade one level down, using this child's resolved.amt as ITS new_parent_amount —
     --   same nine-step algorithm, recursively. A child whose ₹ didn't change (rare now that
     --   re-fit is unconditional, not just "coincidentally landed on its old value) skips this —
     --   nothing changed for it to propagate.
8. SIBLING CHECK: Σ resolved.amt (all children) ≤ new_parent_amount?
     -- should always hold by construction (room_remaining is exactly the unlisted group's
     --   target sum) — kept as the final defensive gate, not the primary mechanism.
     → else reject ALLOCATION_TOTAL_EXCEEDED
9. Commit every row that actually changed — including any grandchildren re-fitted in step 7, in
   the same transaction; push new ceilings to budget_usage
```

**A consequence worth stating plainly, since it can surprise a caller:** an unlisted child's ₹ can
*decrease* even while the parent overall *grows* — the re-fit trigger is always "does
`room_remaining` still cover what the unlisted group currently holds", not "did the parent grow or
shrink". If one explicitly-listed sibling claims more than the parent's entire growth, the other,
untouched siblings can be squeezed and — if that squeeze drops one of them below its own spend —
the *whole call* rejects, even though the parent itself was being increased.

## 3. The Application and Key Budget - Create & Revise

Both `Tenant → Application` and `Application → Key` need the same checks

| Check | Create | Edit |
|---|---|---|
| **Sibling check** — children's % under one parent ≤ 100% | ✅ | ✅ |
| **Floor check** — new ₹ can't fall below what's already spent. An Application's *unlisted* Keys are re-fit against whatever's left and checked instead (Section 2b) | — | ✅ |
| **Cascading recompute** — ₹ recalculated below a changed parent | one-time calc for the new row only | Every level, always, unconditional — Section 2b |
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
  "application_overrides": [               // array, optional — pin specific Applications to an exact
                                            //   value; every OTHER Application is proportionally
                                            //   re-fit against what's left (Section 2b) — no mode to
                                            //   choose, this is the only behavior
    {
      "application_id": "3fa8b8b0-...",    // string (uuid), required
      "allocated_percentage": 58.33,       // number — exactly one of these two
      "allocated_budget": 70000.00,        // number — exactly one of these two
      "api_key_allocations": [             // array, optional — pin specific Keys under THIS
                                            //   Application the same way; its other Keys are
                                            //   re-fit against what's left of ITS new ₹
        {
          "api_key_id": 4821,              // integer, required
          "allocated_percentage": 75.0,    // number — exactly one of these two
          "allocated_budget": 30000.00     // number — exactly one of these two
        }
      ]
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

Accepts a **partial** list either way, and two different rules apply depending on the level:

- **At this call's own scope** (Applications under `tenant_id`, or Keys under `application_id`):
  only the rows you list are touched. Sibling rows you don't mention are left exactly as they are —
  full stop. The Tenant's (or Application's) own total isn't changing in this call at all, so there's
  no pie to reslice for a row you never mentioned; the response reflects only the rows you sent, not
  every row at that level. To explicitly zero one out, list it with `allocated_percentage: 0`.
- **Within a row you DID list and resize**: any of its own un-listed children (a listed Application's
  un-listed Keys) go through the unconditional re-fit rule in Section 2b, same as everywhere else —
  they are NOT left untouched. The response's `api_key_allocations` under that Application therefore
  includes every one of its Keys that has one (explicit or auto-refitted), not just the ones you sent.

No `redistribution_mode` — there is no mode to choose (Section 2b). Listing a child *is* the
override mechanism: give it explicitly to pin its exact value; leave it out to have it proportionally
absorb its share of whatever room the explicit rows *at its own level* didn't claim.

**Request** (scoped by `tenant_id` — editing Applications, optionally their Keys in the same call)
```
PUT /auth/allocations?tenant_id=101
```
```json
{
  "application_allocations": [
    {
      "application_id": "3fa8b8b0-...",   // required in this scope — every row must carry application_id, none may carry api_key_id
      "allocated_percentage": 40.0,       // number — exactly one of these two
      "allocated_budget": 40000.00,       // number — exactly one of these two
      "api_key_allocations": [            // array, optional — explicit edits to THIS Application's own Keys, resolved in the same transaction; any Key under it NOT listed here is proportionally re-fit against what's left of its new ₹ (Section 2b)
        {
          "api_key_id": 4821,             // integer, required — must actually belong to application_id "3fa8b8b0-..." above, or 422 KEY_APPLICATION_MISMATCH
          "allocated_percentage": 75.0,   // number — exactly one of these two
          "allocated_budget": 30000.00    // number — exactly one of these two
        }
      ]
    }
    // as many Application rows as needed; each carries only the Keys being explicitly
    // edited under it — api_key_allocations is never a flat, cross-Application list
  ]
}
```

**Request** (scoped by `application_id` — editing Keys directly; Keys are leaves, no nesting)
```
PUT /auth/allocations?application_id=3fa8b8b0-...
```
```json
{
  "api_key_allocations": [
    {
      "api_key_id": 4821,              // required in this scope — application_id must be absent from every row
      "allocated_percentage": 50.0,    // number — exactly one of these two
      "allocated_budget": 20000.00     // number — exactly one of these two
    }
  ]
}
```

**Response — 200 OK** (tenant-scoped example — array names mirror the request)
```json
{
  "success": true,
  "data": {
    "parent_id": "101",                   // the tenant_id or application_id that scoped this call
    "total_allocated_percentage": 80.0,   // number — live sum across EVERY Application under the
                                           //   tenant (a fresh read, not derived from the rows
                                           //   below) — a summary figure, unrelated to which rows
                                           //   this call happened to touch
    "application_allocations": [          // ONLY the Application(s) listed in the request — a
                                           //   sibling Application never mentioned in this call
                                           //   does not appear here, because it was never touched
      {
        "application_id": "3fa8b8b0-...",
        "allocated_percentage": 40.0,        // number
        "allocated_budget": 40000.00,        // number — recomputed
        "api_key_allocations": [             // EVERY Key under this Application that has one — not
                                              //   just the ones the caller listed, since this
                                              //   Application's own un-listed Keys ARE in scope for
                                              //   the Section 2b cascade (see the two-rule split above)
          {
            "api_key_id": 4821,
            "allocated_percentage": 75.0,     // number
            "allocated_budget": 30000.00,     // number — recomputed
            "auto_refitted": false            // true for a Key the caller never listed but the unconditional re-fit rule touched anyway
          }
        ]
      }
    ]
  }
}
```
No `"scope"` field — the response is already self-describing: `application_allocations` (nested)
for the `tenant_id`-scoped call, flat `api_key_allocations` for the `application_id`-scoped one; a
client doesn't need a discriminator string to tell them apart.

**New errors (on top of the shared table in Section 8):**

| Status | Code | Meaning |
|---|---|---|
| 422 | `MISSING_SCOPE` | neither `tenant_id` nor `application_id` given |
| 422 | `AMBIGUOUS_SCOPE` | both `tenant_id` and `application_id` given |
| 422 | `ROW_SCOPE_MISMATCH` | a row carries the wrong id field for the endpoint's scope (e.g. `api_key_id` at top level when scoped by `tenant_id`) |
| 422 | `KEY_APPLICATION_MISMATCH` | a nested `api_key_id` doesn't actually belong to the `application_id` it's nested under |

---
