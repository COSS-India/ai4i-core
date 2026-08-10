# Budget in AI Switch — Support Both Cost and Tokens

**Status:** Analysis / design
**Services affected:** `platform-core-service`, `kafka-consumers` (payperuse_consumer), `auth-service`, `frontend/simple-ui`

> Wherever this doc says "AI Switch budget", it means
> the PPU wallet (`ppu_tenant_tier_assignments.budget_limit` /
> `available_balance`). I'll use "the wallet" for short.

---

## 1. The ask, in plain words

Today, when an admin sets a spending limit for a tenant, it's always a
**currency amount** (₹10,000). The ticket wants the admin to be able to
choose instead to set the limit as a **token count** (100,000 tokens) — and
for the system to track and cut off usage the same way, just counting tokens
instead of counting rupees.

The two flows called out in the ticket are:

```
Cost mode:    Budget = ₹100  → usage drains it: 100 → 95 → 93 → ... → 0 → mark "Budget Exhausted"
Token mode:   Budget = 1,000,000 tokens → usage drains it: 1,000,000 → 999,999 → ... → 0 → mark "Token Exhausted"
```

And the important constraint: **token counting only makes sense for LLM**
calls (ASR/NMT/TTS/OCR don't produce a "tokens" number). The ask is to build
this so that fact is a piece of *configuration*, not a hardcoded
`if service == "llm"` scattered through the code.

### Scope for this round

- **LLM only.** Other inference types (ASR/NMT/TTS/OCR/...) are explicitly
  out of scope — we're not designing token-mode budgeting for them, and
  their existing cost-mode billing is untouched.
- **Additive, nothing removed.** Currency-mode budgets keep working exactly
  as they do today. This feature just adds a second option — going
  forward, the admin picks **either** Cost **or** Tokens per tenant. Both
  stay fully supported side by side.
- **No backfill, no display sweep in this round.** We are not auditing/
  fixing every existing ₹ label across the app as part of this feature —
  only the specific screens this feature itself adds a toggle to (§4.5).

---

## 2. How the wallet works today (so the change is easy to see)

| Piece | File | What it does today |
|---|---|---|
| The wallet itself | [`ppu_tenant_tier_assignment.py`](../services/platform-core-service/app/models/pay_per_use/ppu_tenant_tier_assignment.py) — `PPUTenantTierAssignment` | Holds `budget_limit` and `available_balance`. Both are plain `Numeric` columns — **there is no currency/unit column today**. Everywhere in the code this number is implicitly ₹ (comments say "₹", schema docstrings say "Budget limit in INR"). |
| Setting the wallet | [`tenant_assignment_service.py`](../services/platform-core-service/app/services/pay_per_use/tenant_assignment_service.py) — `assign_tier`, `reassign_tier`, `revise_budget` | Admin picks a tier + a ₹ number + a date range. `revise_budget` does top-up/top-down. |
| Draining the wallet | [`_billing.py`](../services/kafka-consumers/consumers/payperuse_consumer/_billing.py) — `deduct_balance_and_update_quota()` | Runs on **every** billing event, for **every** inference type. It always does `available_balance = available_balance - :cost`. `cost` is always a ₹ amount computed by `calculate_cost()`, regardless of whether the call was LLM, ASR, NMT, etc. |
| What "cost" is computed from | [`_billing.py`](../services/kafka-consumers/consumers/payperuse_consumer/_billing.py) — `handler.py` | For LLM, the billable quantity is **total tokens** (`input_tokens + output_tokens`); for every other inference type it's the type's own unit (minutes, characters, images...). This total is multiplied by the service's ₹-per-unit price (from `mm_services`) to get `cost`. **This total-tokens-for-LLM rule already exists** — it's just currently only ever turned into ₹, never used as-is. |
| Marking it exhausted | [`api_key_service.py`](../services/auth-service/app/services/api_key_service.py) / [`cache_service.py`](../services/auth-service/app/services/cache_service.py) | Redis hash `auth:apikey:{api_key}` gets a `budget-exhausted` field set to `"1"`. `validation.py::_validate_api_key` checks that flag and returns HTTP 429 on every request until it's cleared. |
| Setting the budget in the UI | [`TenantManagementTab.tsx`](../frontend/simple-ui/src/components/profile/TenantManagementTab.tsx) | "Assign Tier" modal: Tier dropdown + a plain ₹ number input (`clampBudgetInput`) + effective dates. No currency/unit choice exists. |

**Important side-fact:** there is *already* a separate, per-inference-type
**quota** system (`ppu_tier_quotas.monthly_quota` / `ppu_quota_usage`) that
tracks "units used this month" per tenant per inference type — and for LLM
that's already denominated in tokens (see `inference_types.yaml`,
`unit: tokens`). That system is about a **monthly reset-able cap per
service type**, not the ticket's ask, which is about the **overall
spending wallet**. I'm calling this out so we don't confuse the two or
accidentally rebuild something that already exists — see §6 "Out of
scope."

---

## 3. The design

### 3.1 Core idea

Add one new field to the wallet: **`budget_type`**, an enum with two values,
`COST` or `TOKENS`. It's set once, at the same time and place the ₹/token
number is set (Assign Tier / Reassign Tier), and it just says **how to read
the number already sitting in `budget_limit`/`available_balance`** — no new
number column is needed, because "how much is left" is the same concept
either way, just counted in a different unit.

```
budget_type = COST    →  available_balance means "₹ remaining"
budget_type = TOKENS  →  available_balance means "tokens remaining"
```

### 3.2 Draining the wallet — Cost vs Tokens

The billing consumer already computes, for every LLM event, **both**:
- `cost` — the ₹ amount for this event (existing)
- `units` — total tokens for the event, i.e. `input_tokens + output_tokens`
  (existing — this is the "total tokens for LLM" rule already in the code)

The only new logic needed is: **pick which of those two numbers to subtract
from the wallet, based on the tenant's `budget_type`**:

```
if wallet.budget_type == COST:
    subtract cost      (unchanged — this is exactly today's behavior)

if wallet.budget_type == TOKENS:
    subtract units      (the same total-tokens number that already exists,
                         just applied to the balance directly instead of
                         being converted to ₹ first)
```

`budget_type` is a per-tenant setting the admin picks (§4.5), not a code
branch keyed off inference type — that's what makes it "configurable"
rather than a one-off LLM hack: the field, the validation, and the UI toggle
are all generic Cost-or-Tokens plumbing. The reason it only ever fires for
LLM in practice is simply that LLM is the only inference type that produces
a token count at all — per this round's scope, we're not building
equivalent handling for other inference types (see §6).

### 3.3 The exhaustion signal must say which kind — not a generic flag

- The exhaustion check itself stays `available_balance <= 0` —
  unit-agnostic, no change.
- But the signal that gets raised **must distinguish Cost-exhausted from
  Tokens-exhausted** — this is a required part of the design, not a
  cosmetic message tweak. Today's Redis hash sets a single generic
  `budget-exhausted` field; that's no longer enough once a tenant can be
  exhausted for two different reasons.
- Design: the Kafka consumer's exhaustion write carries a **reason**
  (`cost` or `tokens`) alongside the boolean flag, all the way through:
  `_post_billing` callback payload → Redis hash (new companion field,
  e.g. `budget-exhausted-reason`) → auth-service's 429 response body.
  Concretely: `budget-exhausted: "1"` + `budget-exhausted-reason: "tokens"`
  → auth-service returns `TOKEN_BUDGET_EXHAUSTED` / "Token Budget
  Exhausted" instead of the generic `BUDGET_EXHAUSTED` / "Budget
  Exhausted" it returns today for Cost mode. See §4.3/§4.4.

---

## 4. What changes, where

### 4.1 Database

To be precise about what "the wallet" actually is: `ppu_tenant_tier_assignments`
is a **Postgres table**, living in the **`ai4iplatform_core` database**
(the Postgres database `platform-core-service` owns — not a schema name,
despite the folder naming below). It's mapped in Python by the
`PPUTenantTierAssignment` model class in
[`ppu_tenant_tier_assignment.py`](../services/platform-core-service/app/models/pay_per_use/ppu_tenant_tier_assignment.py).

| Change | Type | Where |
|---|---|---|
| New column `budget_type` (enum `COST`/`TOKENS`, default `COST`) | Postgres column on the `ppu_tenant_tier_assignments` table | Added via a new Alembic **migration file** under [`infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_core/`](../infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_core/) (that folder is named after the `ai4iplatform_core` database it targets) |
| Matching field on the model class | Python/SQLAlchemy column declaration | `PPUTenantTierAssignment` class, same file as above (see §4.2) |

Default `COST` means every existing row keeps behaving exactly as it does
today — **this change is purely additive, no backfill logic needed.**

### 4.2 `platform-core-service` (backend, admin API)

| File | Change |
|---|---|
| `app/models/pay_per_use/ppu_tenant_tier_assignment.py` | Add `budget_type` column + Python enum |
| `app/services/pay_per_use/tenant_assignment_service.py` (`assign_tier`, `reassign_tier`, `revise_budget`) | Accept and validate `budget_type`; tokens should be validated as whole numbers ≥ 0 (no decimals), cost keeps its existing decimal validation |
| `app/schemas/pay_per_use/*` (Pydantic request/response models) | Add `budget_type` field to assign/reassign/revise payloads and to the tenant tier assignment response |
| Whatever route exposes tier assignment / tenant spend (`routes/pay_per_use/*`) | Pass `budget_type` through so the frontend can render the right label/unit |

**Decision needed:** should `budget_type` be changeable on an *existing*
active assignment (`revise_budget`), or only settable when a *new*
assignment is created (`assign_tier`/`reassign_tier`)? Flipping the meaning
of a balance mid-cycle (₹50,000 silently becoming "50,000 tokens") is
confusing and easy to get wrong. **Recommendation:** don't allow changing
`budget_type` on a live assignment — require closing it and creating a new
one, same as `reassign_tier` already does when switching tiers.

### 4.3 `kafka-consumers` (payperuse_consumer) — where the actual draining happens

| File | Change |
|---|---|
| `_billing.py` — `deduct_balance_and_update_quota()` | Needs to know the tenant's `budget_type` before deciding whether to subtract `cost` or `units`. Cleanest way: pull `budget_type` in the same `wallet_update` CTE that already reads the assignment row, so it's still one round trip. |
| `handler.py` — `_bill_usage` (or wherever it calls the above) | For LLM events (`pricing.task_type == "llm"`), pass both `cost` and `units` through as today; the deduction function picks one based on `budget_type`. No change to how other inference types are billed. |
| `_post_billing` (budget-exhausted callback) | **Required change:** add a `reason` field (`"cost"` \| `"tokens"`) to the callback payload sent to `POST /internal/ppu/tenant/{tenant_id}/budget-exhausted` — this is what lets auth-service (§4.4) raise the right flag instead of one generic one. |

**This is the highest-risk file to touch** — it's the single write path for
every tenant's balance, for every inference type, so a mistake here affects
billing correctness for the whole platform, not just token-budget tenants.
Needs solid test coverage on both branches (§7) before shipping.

### 4.4 `auth-service`

| File | Change |
|---|---|
| `services/api_key_service.py` / `cache_service.py` | **Required change:** `set_budget_exhausted_for_tenant()` now also writes a companion `budget-exhausted-reason` field (`"cost"` \| `"tokens"`) onto the `auth:apikey:{api_key}` Redis hash, using the `reason` now arriving on the internal callback (§4.3). Same existing fan-out to every cached API-key hash for the tenant — just one more field written alongside the boolean. |
| `routes/validation.py` (`_validate_api_key`) | **Required change:** read the new reason field and return a distinct error code/message per case — `TOKEN_BUDGET_EXHAUSTED` / "Token Budget Exhausted" vs the existing `BUDGET_EXHAUSTED` / "Budget Exhausted" — instead of one generic 429 for both. |

### 4.5 Frontend (`frontend/simple-ui`)

| File | Change |
|---|---|
| `components/profile/TenantManagementTab.tsx` | "Assign Tier" modal: add a Cost / Tokens toggle next to the budget number field. Swap the input's label/prefix (₹ vs "Tokens") and validation (`clampBudgetInput` needs a tokens variant — integers, different max) based on the toggle. Same for the "Manage Plan" top-up/top-down flow. |
| `services/tierManagementService.ts` | Add `budget_type` to `AssignTenantTierPayload`, `TenantTierAssignment`, and the revise-budget payload types. |
| `hooks/useTenantManagement.ts` | Thread the new field through form state and submit handlers. |
| `components/metering/SpendOverviewPanel.tsx`, `TenantSpendPanel.tsx` | Read `budget_type` from the API response and format this tenant's own balance accordingly ("₹1,234 remaining" vs "1,234 tokens remaining"). Scoped to these two panels only — not a wider audit of every ₹ label in the app. |

### 4.6 `inference-service`

**No change needed.** `input_tokens`/`output_tokens` are already captured
and put on the `ai-inference` span for every LLM call today (`llm_service.py`
→ `get_llm_usage()`). The consumer already receives everything it needs;
this feature only changes how that existing data is *used* downstream.

---

## 5. Open questions (need a product decision before building)

1. **Can `budget_type` change mid-cycle?** Recommend no (§4.2) — require a
   fresh assignment instead, same as switching tiers already works.
2. **What does "Tokens" mean for `revise_budget` (top-up/top-down)?** Same
   mechanics as Cost mode (add/subtract a whole number of tokens instead of
   ₹) — just confirming there's no extra rule needed here before building.

---

## 6. Out of scope / not to be confused with this feature

- **Other inference types (ASR/NMT/TTS/OCR/...).** Per this round's
  direction, this feature is LLM only. Their billing (always cost-mode)
  is completely untouched — no design or code change for them.
- **No backfill, no display sweep.** Existing rows default to `COST`
  automatically (§4.1); we're not auditing other ₹ displays across the app
  beyond the two panels named in §4.5.
- The existing **per-inference-type monthly quota** system
  (`ppu_tier_quotas.monthly_quota`, `ppu_quota_usage`) already tracks token
  usage for LLM today. This feature doesn't touch it — it's a separate,
  already-working mechanism for a different purpose (monthly reset-able cap
  per service type, not the overall wallet).
- `auth-service`'s `TenantPlan`/`_assign_plan_to_tenant` path
  (`tenant_service.py`) calls a `billing/policies` endpoint that doesn't
  exist in `platform-core-service` — this looks like dead/superseded code
  from an earlier design. Don't build on it; it's unrelated to the `ppu_*`
  tables this feature actually touches.

---

## 7. Risks / blockers

- **`deduct_balance_and_update_quota()` is a shared hot path** for all
  billing, all tenants, all inference types — even though this feature only
  adds a Tokens *option* for LLM, the function itself is called for every
  inference type. Changes there need regression tests confirming non-LLM
  and existing Cost-mode LLM billing behave exactly as before.
- No blockers found that would stop this from being built — no missing
  infra, no conflicting in-flight work on the wallet found in the codebase.

---

## 8. Testing checklist

- Existing cost-mode tenants (LLM and non-LLM): confirm zero behavior
  change (regression).
- New token-mode tenant, LLM usage: balance drains by total tokens,
  exhausts at 0, Redis flag set **with `reason = "tokens"`**, 429 returned
  with the token-specific message (not the generic cost one).
- Cost-mode tenant exhaustion still sets `reason = "cost"` and returns the
  existing cost message — confirm the two never get swapped.
- Non-LLM billing events: confirm completely unaffected by this change,
  regardless of any tenant's `budget_type`.
- New assignments default to `budget_type = COST` unless the admin
  explicitly picks Tokens.
- `revise_budget` (top-up/top-down) works correctly in both modes.
