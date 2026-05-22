# Audit Logs — Quick Notes

My own notes on what audit logging exists in the repo today, and whether it makes sense to pull it out into a shared library or a new service.

## Which services have audit logs?

Only two:

- **pii-service** — writes audit rows
- **policy-service** — reads audit rows

The other five I checked have **no audit logging at all**:

- auth-service (the word "audit" appears once in a comment about `created_at`/`created_by` columns — not real audit logging)
- platform-core-service
- inference-service
- smr-service
- request-profiler

## What does pii-service log?

It writes one audit row every time `/redact` runs successfully. Fields:

| Field | What it is |
|---|---|
| `trace_id` | OpenTelemetry trace ID (links to logs/traces) |
| `tenant_id` | Tenant who made the request |
| `domain_id` | Which domain the redaction was for, e.g. "logistics" — a string, not a real ID |
| `target_context` | Value of the `X-Target` header (default `"user"`) |
| `pii_count` | How many PII entities were detected |
| `processing_ms` | How long the redaction took |
| `trace_json` | List of step status messages (e.g. "AI identified 3 entities") |
| `created_at` | Timestamp |

**Table:** `audit_logs`

What is **not** stored: no `user_id`, no input text, no detected text, no action verb, no resource ID.

## What does policy-service log?

It doesn't write — it just exposes two read endpoints. Fields it reads:

| Field | What it is |
|---|---|
| `pii_audit_id` | UUID primary key |
| `trace_id` | OTel trace ID |
| `tenant_id` | Tenant |
| `policy_id` | UUID, foreign key to the PII policy that was applied |
| `target_context` | Same as pii-service |
| `pii_count` | Same |
| `processing_ms` | Same |
| `trace_json` | Same |
| `created_at` | Same |

**Table:** `pii_audit_logs`

## They use different tables?

Yes. pii-service writes to `audit_logs`. policy-service reads from `pii_audit_logs`. Same general idea, **different physical tables**.

Also, the column that ties the row to "what policy was applied" is different:

- pii-service writes `domain_id` (free-form string, no foreign key)
- policy-service expects `policy_id` (UUID with a real foreign key to the policy table)

So they can't even describe the same rows. They're two parallel mini-audit systems that look similar but aren't connected.

## What event is being audited?

Just one: **"PII redaction was performed for this tenant in this domain."**

That's the only thing recorded. No logins, no policy edits, no model invocations, no permission denials, nothing else.

## Can this structure be reused for other services?

Not directly. The current schema is PII-specific and is missing the basics most audit logs need:

- **No `user_id`** — only `tenant_id`. Can't tell *which user* did something.
- **No action name** — the row implicitly means "PII detection happened." No field for `"login"`, `"policy.update"`, etc.
- **No resource reference** — no `resource_type` / `resource_id` to say what was acted on.
- **No before/after state** — useful for any change-tracking audit (e.g. role changes).
- **No outcome field** — can't tell `success` vs `denied` vs `failed`.

For PII events, fine. For anything else, you'd be cramming data into `domain_id` and `trace_json`, which won't hold up.

## If we build a shared audit library or service — what fields should it have?

Minimum fields to cover any audit use case across the platform:

| Field | Why |
|---|---|
| `event_id` (UUID) | Unique ID for dedup on retries |
| `occurred_at` | When the action happened (producer clock) |
| `received_at` | When the row was persisted (server clock) |
| `tenant_id` | Required — every event belongs to a tenant |
| `actor_type` | One of `user`, `service`, `system` |
| `actor_id` | User UUID, service name, etc. |
| `action` | Verb like `auth.login`, `pii.redact`, `policy.update` |
| `resource_type` | What was acted on (e.g. `policy`, `user`) |
| `resource_id` | ID of that thing |
| `outcome` | One of `success`, `denied`, `failed` |
| `source_service` | Which service emitted the event |
| `trace_id` | OTel correlation (optional) |
| `request_id` | HTTP correlation (optional) |
| `before` | JSON, optional — state before the change |
| `after` | JSON, optional — state after the change |
| `metadata` | JSON, optional — anything else (counts, durations, headers) |

The existing pii-service fields (`pii_count`, `processing_ms`, step messages) all fit inside `metadata` if we ever migrate.

## My take

Two paths, depending on what we want:

1. **If audit stays PII-only** — leave it alone, just fix the two tables not matching each other.
2. **If we want platform-wide audit** — use the field list above as the new schema. Build either a shared `ai4icore_core.audit` module or a dedicated audit service, and have producers (auth-service for logins, policy-service for policy edits, inference-service for model calls, etc.) write to it.

A shared library is the cheaper start. A dedicated service is the right shape only once 3+ services are actually emitting events.

## Source files (for reference)

- pii-service writer: [services/pii-service/main.py](services/pii-service/main.py), [services/pii-service/audit_worker.py](services/pii-service/audit_worker.py)
- policy-service reader: [services/policy-service/app/models/orm.py](services/policy-service/app/models/orm.py), [services/policy-service/app/api/routes/audit_logs.py](services/policy-service/app/api/routes/audit_logs.py)
