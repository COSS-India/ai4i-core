# Budget: Cost or Tokens


**What:** Let an admin set a tenant's budget as **either** ₹ (Cost) **or** a token count (Tokens) — LLM only. Currency stays fully supported; Tokens is a new, additional option.

---

## 1. Key changes at a glance

### 1.1 Database change — exactly what it is

| What | Type | Name / Location |
|---|---|---|
| Database | Postgres database (owned by `platform-core-service`) | `ai4iplatform_core` |
| Table | one row per tenant's tier assignment | `ppu_tenant_tier_assignments` |
| New column | Postgres column, type enum, values `COST` \| `TOKENS`, default `COST` | `budget_type` |
| ORM mapping (Python side) | SQLAlchemy **model file/class** — the code representation of the table above, needs the matching column added | [`services/platform-core-service/app/models/pay_per_use/ppu_tenant_tier_assignment.py`](../services/platform-core-service/app/models/pay_per_use/ppu_tenant_tier_assignment.py) → class `PPUTenantTierAssignment` |
| Migration | New Alembic **migration file** (a script that runs `ALTER TABLE ppu_tenant_tier_assignments ADD COLUMN budget_type ...`) | New file under [`infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_core/`](../infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_core/) — that folder is named after the `ai4iplatform_core` database, it's not a schema name |

In short: **one new column, on one existing table, in one existing
database** — applied via one migration file, mirrored by one edit to the
existing Python model class. No new table, no new database, no backfill
(the `COST` default covers every existing row automatically).

### 1.2 Everything else, at a glance

| Area | Change |
|---|---|
| **Modules touched** | `platform-core-service` (model, service, schema, API), `kafka-consumers` payperuse_consumer (deduction logic + reason on exhaustion callback), `auth-service` (Redis reason field + distinct 429 message), `frontend/simple-ui` (toggle + display). |
| **No change** | `inference-service` (already emits token counts today). |
| **Core logic change** | Billing consumer already computes both `cost` (₹) and `units` (total tokens) per LLM event. Only new logic: subtract `cost` if `budget_type == COST`, subtract `units` if `budget_type == TOKENS`. Exhaustion check (`balance <= 0`) stays identical. |
| **Redis flag — not generic anymore** | Today's Redis flag (`budget-exhausted: 1`) is one generic signal. It now must carry **which kind** was exhausted: a new companion field `budget-exhausted-reason` (`cost` \| `tokens`), set by the same consumer call, read by auth-service to return a distinct message — "Budget Exhausted" (cost) vs "Token Budget Exhausted" (tokens) — instead of one shared message for both. |

---

## 2. LLM-only validation — where does it happen?

**Neither auth-service nor inference-service.** The "is this call LLM?" check happens **only in the async Kafka billing consumer**, reusing a service-metadata field (`task_type`) it already loads and caches for every billing event — nothing new to fetch.

- **inference-service**: no check needed — LLM traffic already goes through its own dedicated code path (the LLM proxy), so it's inherently LLM-scoped. No new LLM-detection logic to add there.
- **auth-service**: still does **no LLM-detection** of its own — it never decides Cost vs Tokens or LLM vs non-LLM itself. It only reads whatever the Kafka consumer already decided off the Redis flag (§1.2) and surfaces the matching message.
- **Kafka consumer**: the one place that decides *what to do* with `budget_type`, using `task_type` metadata it already has cached. For non-LLM events on a `TOKENS`-mode tenant, the budget is simply left untouched.

## 3. Latency impact

| If the LLM-check lived in... | Impact |
|---|---|
| **auth-service** (current, unchanged) | Would add a lookup to **every request, every tenant, every service** — auth-service gates 100% of traffic, so this is the worst possible place to add work. **We are not doing this.** |
| **inference-service** | Would add a synchronous check to the LLM request's critical path (user is already waiting on the LLM call) and would duplicate budget-state logic that the Kafka consumer owns — risk of race conditions with concurrent requests. |
| **Kafka consumer (proposed candidate)** | **Zero added latency on any user-facing request** — this runs async, after the response is already returned. Trade-off: a small, pre-existing propagation delay before the exhaustion flag takes effect (same eventual-consistency window Cost-mode already has today — not a new risk). |

## 4. Alternatives considered

1. **Inline check in inference-service** — feasible (it already knows it's an LLM call), but adds latency to the live request and creates a second place that reads/writes budget state → consistency risk. Rejected.
2. **Inline check in auth-service** — auth-service can't know actual token usage before the call happens anyway (only known after the LLM responds), so it could only ever do a coarse pre-check — and it's the highest-traffic, most latency-sensitive service in the platform. Rejected.
3. **Async check in Kafka consumer (proposed candidate)** — reuses metadata already loaded there, no new latency anywhere, single writer for budget state (no race risk), and mirrors exactly how Cost-mode billing already works today. **This is the approach in the design.**

The proposed approach adds zero latency to real requests, doesn't duplicate the budget's single source of truth, and requires no new data fetch — it slots into logic and metadata that already exist.
