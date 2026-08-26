# API Key Allocation & Reallocation — Design

## Assumptions (things the source diagram doesn't say explicitly)

- Every key must belong to an Application — no exceptions. Adopter-admin/test keys go under a seeded **System Application** instead of being unattached.
- `allocated_percentage = NULL` means "no cap at this level" (bounded by the parent instead). It is never treated as `0` (which means fully blocked).
- Revoking a key freezes its allocation — it does **not** free up its % automatically. An explicit "release" action is needed to give that % back to the Application.
- Two admins editing allocations for the same Application at the same time must not both succeed into an invalid total → needs a lock.
- `applications`/`api_key` (ceilings) live in **auth DB**. `budget_usage` (actual spend) lives in **core DB**. These two are never in the same transaction.

---

## 1. High-Level Design

**Goal:** Let an admin give each API key a % share of its Application's budget, safely — never over-allocated, never shrunk below what's already spent, and never corrupted by two people editing at once.

```
Institution (tenant)
   allocated_budget = ₹1,00,000
        │
        ▼
   Application "A"
   allocated_percentage = 50%   →  allocated_budget = ₹50,000
        │
        ├── Key 1: allocated_percentage = 60%  → allocated_budget = ₹30,000
        └── Key 2: allocated_percentage = 40%  → allocated_budget = ₹20,000
                                                     (60% + 40% ≤ 100% ✓)
```

```
 AUTH DB                          CORE DB
┌─────────────┐                 ┌───────────────┐
│ applications│                 │ budget_usage   │
│ api_key     │ ── ceiling ───► │ (spend ledger) │
│ (ceilings)  │ ◄── spend* ──── │                │
└─────────────┘   (*edit only) └───────────────┘
```

**Create flow (plain words):**
1. Admin picks an Application, gives the new key a %.
2. System checks: existing keys' % + new key's % ≤ 100% of the Application.
3. System calculates the key's ₹ ceiling and saves the key (auth DB).
4. System copies that ₹ ceiling into the core DB spend table, so billing never has to cross databases.

**Reallocate flow (plain words):**
1. Admin changes a key's %.
2. System re-checks the sibling total (excluding this key) + new % ≤ 100%.
3. System checks the new ₹ ceiling is still ≥ what this key has already spent (read from core DB).
4. If both pass → save the new % and ceiling, and re-sync the copy in core DB.

---

## 2. Low-Level Design

### Schema (only what's new/relevant)

| Table | Key columns | Notes |
|---|---|---|
| `applications` (auth) | `allocated_percentage`, `allocated_budget` | % is entered by admin; budget is auto-calculated |
| `api_key` (auth) | `application_id` (NOT NULL), `allocated_percentage`, `allocated_budget`, `is_active`, `version` | `version` = used to catch concurrent edits |
| `budget_usage` (core) | `api_key_id` (unique), `api_key_budget_snap`, `api_key_budget_used` | one row per key; `snap` = copy of the ceiling, `used` = actual spend |

### Validation rules

- **Sibling check:** sum of all active keys' % under one Application ≤ 100%.
- **Floor check** (edit only): new ceiling ≥ `api_key_budget_used` (can't shrink below what's spent).
- **Locking:** one lock per Application, held while checking + saving — stops two concurrent edits from both passing.
- **Concurrency token:** every edit must pass the `version` it last read; mismatch = someone else edited first → reject and ask client to retry.

### Edge cases

| Case | Behaviour |
|---|---|
| Key has no % set | No ceiling at key level; Application's ceiling still applies |
| Key is revoked | Its % still counts against the sibling total until explicitly released |
| Application's budget is cut below what its keys need | Rejected — Application-level check happens before key-level checks |
| Core DB briefly unreachable during create/edit | Save still succeeds in auth DB; ceiling copy syncs later via a background retry (~60s) |

---

## 3. API Contract

### Create API Key

```
POST /v1/institutions/{tenantId}/api-keys
```

**Request**
```json
{
  "name": "reporting-bot",
  "applicationId": "3fa8b8b0-52a1-4d9a-9c1e-7f0a2b6d1234",
  "allocatedPercentage": 30.0
}
```

**Response — 201 Created**
```json
{
  "id": 4821,
  "name": "reporting-bot",
  "applicationId": "3fa8b8b0-52a1-4d9a-9c1e-7f0a2b6d1234",
  "allocatedPercentage": 30.0,
  "allocatedBudget": 15000.00,
  "isActive": true,
  "version": 1,
  "createdAt": "2026-08-25T09:14:02Z"
}
```

**Errors**

| Status | Code | Meaning |
|---|---|---|
| 422 | `APPLICATION_REQUIRED` | `applicationId` missing |
| 422 | `APPLICATION_NOT_IN_INSTITUTION` | Application belongs to a different tenant |
| 422 | `ALLOCATION_TOTAL_EXCEEDED` | this key's % would push siblings over 100% |

---

### Edit / Reallocate API Key

```
PATCH /v1/api-keys/{keyId}/allocation
```

**Request**
```json
{
  "allocatedPercentage": 25.0,
  "expectedVersion": 1
}
```

**Response — 200 OK**
```json
{
  "id": 4821,
  "allocatedPercentage": 25.0,
  "allocatedBudget": 12500.00,
  "version": 2
}
```

**Errors**

| Status | Code | Meaning |
|---|---|---|
| 409 | `ALLOCATION_VERSION_CONFLICT` | `expectedVersion` is stale — someone else edited this key; re-fetch and retry |
| 422 | `ALLOCATION_TOTAL_EXCEEDED` | new % would push siblings over 100% |
| 422 | `ALLOCATION_BELOW_CONSUMED` | new ceiling is below what's already spent |
| 409 | `APPLICATION_BUDGET_OVERCOMMITTED` | the Application itself is already over budget — fix that first |

`ALLOCATION_BELOW_CONSUMED` error body:
```json
{
  "error": "ALLOCATION_BELOW_CONSUMED",
  "apiKeyId": 4821,
  "consumedAmount": 13200.00,
  "requestedBudget": 12500.00
}
```

---

### Bulk Reallocate (all keys under one Application)

```
PUT /v1/applications/{applicationId}/key-allocations
```

**Request**
```json
{
  "allocations": [
    { "apiKeyId": 4821, "allocatedPercentage": 20.0 },
    { "apiKeyId": 4822, "allocatedPercentage": 30.0 }
  ],
  "expectedApplicationVersion": 7
}
```

**Response — 200 OK**
```json
{
  "applicationId": "3fa8b8b0-52a1-4d9a-9c1e-7f0a2b6d1234",
  "allocations": [
    { "apiKeyId": 4821, "allocatedPercentage": 20.0, "allocatedBudget": 10000.00, "version": 2 },
    { "apiKeyId": 4822, "allocatedPercentage": 30.0, "allocatedBudget": 15000.00, "version": 3 }
  ],
  "totalAllocatedPercentage": 50.0
}
```

**Errors:** same codes as single-key edit, applied to the whole set.

---

### Release Allocation (free up a revoked key's %)

```
POST /v1/api-keys/{keyId}/release-allocation
```

**Response — 200 OK**
```json
{
  "id": 4821,
  "allocatedPercentage": 0.0,
  "allocatedBudget": 0.0,
  "version": 3
}
```

**Errors**

| Status | Code | Meaning |
|---|---|---|
| 409 | `KEY_STILL_ACTIVE` | key must be revoked (`is_active = false`) before releasing its allocation |
