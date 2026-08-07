# How Do We Avoid Requiring SMTP? — Analysis & Plan

**Status:** Analysis / plan — no code changed yet
**Service affected:** `auth-service` (primarily), `frontend` (secondary, follow-on)
**Trigger:** A discussion on onboarding adopters without SMTP/email support, and a blocked attempt to exercise tenant onboarding purely over the API

## 1. The ask, in plain words

Some adopters won't have SMTP/email set up when they first stand up the
platform. Three flows currently assume a working mailbox:

| # | Flow | Why email is involved today |
|---|---|---|
| 1 | **Tenant / tenant-user setup** | Tenant admins and tenant users are created **passwordless** (`email_kind="setup"`). The emailed set-password link is the only way they get a first password and activate. |
| 2 | **Self-signup email verification** | `/auth/register` proves the caller owns the email address before the account goes live. |
| 3 | **Forgot / reset password** | The reset link is emailed to the registered address — the only channel we currently trust to re-establish identity after a lost password. |

The concrete trigger was an attempt to script "create tenant → activate →
log in" purely over the API, with no log/DB access, which got stuck at
tenant-user creation. This doc explains *why*, and separately what to do
about flows 2 and 3.

## 2. The good news: nothing actually breaks today when SMTP is down

Before proposing anything, it's worth being precise about what "SMTP not
available" currently does — because it's less than it sounds like.

Every outbound email in `auth-service` goes through the same helper:

```
enqueue_email(background_tasks, email_client, factory)
  → background_tasks.add_task(email_client.send_safe, message)
```

[`EmailClient.send_safe`](../libs/ai4i_core/ai4i_core/email/client.py) never
raises — a provider failure (no `SMTP_HOST`, connection refused, auth
failure, timeout) is caught, logged, and swallowed. And
[`enqueue_email`](../services/auth-service/app/services/email_helpers.py)
runs the send as a **FastAPI `BackgroundTask`** — after the response is
already returned to the caller. So:

- `POST /auth/register`, `/auth/tenants`, `/auth/tenants/{id}/users`,
  `/auth/forgot-password`, `/auth/resend-*` all **succeed (2xx) and commit
  their DB rows regardless of whether the email actually sends.**
- There's also a built-in dev fallback: if `EMAIL_PROVIDER=smtp` but
  `SMTP_HOST` is empty and `ENVIRONMENT=development`,
  [`build_provider`](../libs/ai4i_core/ai4i_core/email/providers/factory.py)
  auto-switches to `ConsoleEmailProvider`, which just logs the rendered
  email (subject/body/token) to stdout instead of sending it. That's
  exactly the "grep the logs for `[ConsoleEmailProvider] would send email`"
  step in the runbook.

**So the real problem is not stability — it's that the token/link a human
needs next has exactly one delivery channel (a real inbox), and no
SMTP-less adopter has that channel.** Everything below is about giving that
token a second, API-visible channel where it's safe to do so.

## 3. Flow 1 — Tenant / tenant-user setup: closer to solved than it first looked

This is where the scripted attempt got stuck, and reading the code shows the
two blockers reported are not quite what they look like.

### 3.1 "We need an endpoint to activate a tenant" — no, we don't

[`ALLOWED_TENANT_STATUS_TRANSITIONS`](../services/auth-service/app/services/tenant_lifecycle.py)
deliberately does **not** allow `PENDING → ACTIVE` through
`PATCH /tenants/{id}/status` (only `PENDING → DEACTIVATED`). That's not an
oversight — activation is intentionally tied to the admin actually setting
a password, not to a bare status flip:

> `AuthService.set_password_with_token`: *"Tenant contact admins: tenant
> moves PENDING → ACTIVE here, then welcome email."*

Adding a manual "activate" endpoint would let a tenant become `ACTIVE` with
**no admin credentials at all**, which is worse than the current gap —
`create_tenant_user` already requires `tenant.status == ACTIVE`
([`_assert_tenant_active_for_user_creation`](../services/auth-service/app/services/tenant_service.py)),
precisely so a tenant can't accumulate users before someone has proven they
can log in. **Recommendation: don't build this. It would remove a safety
check, not add a feature.**

### 3.2 The actual gap: `POST /auth/tenants` doesn't return the setup token

This is the one real blocker. Compare the two "create" endpoints:

| Endpoint | Returns `setup_token`? | Where |
|---|---|---|
| `POST /auth/tenants/{tid}/users` (add a user to an already-active tenant) | ✅ Yes — `TenantUserCreateResponse.setup_token` | [`schemas/tenant.py:223-226`](../services/auth-service/app/schemas/tenant.py) |
| `POST /auth/tenants` (create tenant **+ its first admin**) | ❌ No — `TenantResponse` has no token field | [`routes/tenants.py:29-37`](../services/auth-service/app/routes/tenants.py), [`schemas/tenant.py:181-198`](../services/auth-service/app/schemas/tenant.py) |

`TenantService.create_tenant` calls the exact same `provision_user(...,
email_kind="setup")` internally and gets a token back — the token exists,
it's just discarded before the HTTP response is built. This is why the
scripted flow in the runbook works fine from step 3 onward (tenant *users*)
but dies before it: there's no tenant to add a user to yet, because the
tenant's own admin can't get a token to activate it.

**Fix is a one-field addition, not a new endpoint or a schema/permission
redesign:** add a `TenantCreateResponse(TenantResponse)` with an optional
`setup_token`, populated only from `create_tenant`'s response (not from
`GET`/`PATCH` tenant, which must keep hiding it). This is exactly the same
trust boundary already accepted for tenant-user creation: the caller of
`POST /auth/tenants` is already an authenticated platform `ADMIN` — the one
role permitted to create tenants at all — so handing them the token
directly is no bigger a exposure than the existing tenant-user response.

With that one change, the same scripted flow works end-to-end with zero
email, zero log access, zero DB access:

```
1. POST /auth/login          (platform admin)              → admin JWT
2. POST /auth/tenants         (admin JWT)                    → tenant + setup_token   ← the fix
3. POST /auth/set-password    ({token: setup_token, ...})    → tenant admin activated, tenant → ACTIVE
4. POST /auth/login           (as tenant admin)               → tenant admin JWT
5. POST /auth/tenants/{tid}/users (tenant admin JWT)          → setup_token (already returned today)
6. POST /auth/set-password    (for that user)                → activated
7. POST /auth/login           (as that user)                  → JWT
```

### 3.2.1 Important nuance: this fix is a manual relay, not a replacement for email

It's worth being explicit about *how* the setup link would actually reach
the tenant's real contact person once this ships — because the mechanism
changes, but a human step doesn't go away.

Today: `create_tenant` mints the token, persists it, and enqueues a
best-effort email to the tenant's contact address — that email is the
*only* leg the token travels. Nothing in the change removes that; the email
attempt should keep firing exactly as it does today, so adopters who
already have SMTP see no change in behavior.

What the fix adds is a **second copy of the same link, handed to the caller
of `POST /auth/tenants` in the HTTP response** — i.e. to whichever platform
admin is creating the tenant, not to the tenant's contact person directly.
That admin then has to get it to the actual tenant admin themselves, over
whatever out-of-band channel already exists between the platform team and
that adopter (Slack, a support ticket, a phone call, reading it out loud).
Concretely:

1. Platform admin calls `POST /auth/tenants` → response now includes the
   fully-built setup URL (not just the bare token — the endpoint should do
   the same `{SETUP_LINK_BASE_URL}?token=...` construction `render_setup_link`
   already does for the email, so the admin gets something clickable, not
   an assembly problem).
2. The background email send still fires in parallel, and still silently
   no-ops if SMTP isn't configured — same as today.
3. **The platform admin manually delivers the link** to the tenant's
   contact person through whatever channel got that adopter this far in the
   first place.
4. The tenant admin opens the link, lands on the existing set-password
   page, and everything downstream (`POST /auth/set-password`, tenant
   `PENDING → ACTIVE`) is unchanged.

So this trades "the only copy of the link is stuck in an email that may
never arrive" for "a trusted admin has a copy and must remember to forward
it" — a real improvement (nothing is silently lost), but still a manual
step, not automated delivery. It scales fine for a handful of pilot
adopters; if SMTP-less onboarding is expected to be a *sustained* mode of
operation rather than a bridge until SMTP gets configured, that manual-relay
reality is the strongest argument for not deferring the per-tenant flag in
§6.3 — it's what would let "copy this link and send it yourself" become a
first-class, UI-visible state instead of a workaround every admin has to
remember on their own.

### 3.3 Same idea, for the "user already exists, link expired/lost" case

`resend-setup-link` and `resend-setup-link` (tenant-user variant) already
exist and already re-mint a token — but both **only email it**
([`AuthService.resend_setup_link`](../services/auth-service/app/services/auth_service.py),
[`TenantService.resend_tenant_user_setup_link`](../services/auth-service/app/services/tenant_service.py)).
For an SMTP-less adopter this is a dead end today. Since both callers are
already authorization-checked (platform staff, or the tenant's own admin —
see `_caller_may_access_tenant_for_setup_resend` /
`enforce_scope` + `_deny_moderator`), the fix is the same shape as 3.2:
**return the freshly-issued token in the response body** alongside the
existing "email sent" message, instead of only enqueuing the email. The
email send stays as-is (works fine once SMTP *is* configured; harmless
no-op today) — this just stops the token from being a dead letter when it
isn't.

## 4. Flow 2 — Self-signup verification (`/auth/register` → `/auth/verify-email`)

This one is structurally different from Flow 1, and harder to bypass safely.

In Flow 1 there's always a trusted admin actor in the loop who can be
handed the token directly (the platform admin creating a tenant, the tenant
admin adding a user). In self-signup there's **no such actor** — the whole
point of email verification here is to prove an anonymous caller controls
the address before we trust them. Returning the verify token straight back
in the `/auth/register` response, the way we're proposing for Flow 1, would
defeat that: anyone could "verify" any email address they can merely type,
which is exactly the abuse email verification exists to prevent.

Two honest options, not a fix:

- **A — Scope self-signup out of the SMTP-less story.** Every onboarding
  path this thread actually cares about (tenant + tenant-users) is already
  admin-driven, not self-signup. If SMTP-less adopters only ever provision
  users via a tenant admin (Flow 1), self-signup verification simply never
  has to run for them. This is almost certainly the right near-term answer
  — confirm with product whether plain self-signup (no `tenant_id`) is even
  a path real adopters use, or whether it's a leftover/demo path.
- **B — Add a second ownership-proof channel** (e.g. SMS OTP to a verified
  phone number, or a manual "pending signups" approval queue for a platform
  admin to eyeball and activate). Both are real projects — a new delivery
  provider, or a new admin UI + audit trail — not a config toggle. Only
  worth doing if (A) turns out to be false, i.e. some adopters genuinely
  need anonymous self-signup with no email.

**Recommendation: go with (A) now, revisit (B) only if a real adopter needs
open self-signup without email.**

## 5. Flow 3 — Forgot / reset password

This is the hardest of the three, for a good reason: by definition the user
has already lost their one factor (password), so email is doing real
security work as the *second* channel to re-establish identity. It can't be
bypassed the same way Flow 1 was (handing the token to the user themselves
— they're the one who's locked out).

What it **can** borrow from Flow 1 is the "trusted admin relays it
out-of-band" pattern:

- Add an **admin-initiated** reset variant — a `TENANT_ADMIN` resetting one
  of their own tenant's users, or a platform `ADMIN` resetting anyone —
  that reuses the existing `RESET` token machinery
  (`request_password_reset` / `TokenType.RESET`) but **returns the token in
  the response** to the admin instead of only emailing the user. The admin
  then relays it via whatever channel the adopter actually has (Slack,
  phone, in person) — the same trust boundary as the tenant-onboarding
  runbook already uses today, just made official instead of requiring raw
  SQL.
- This should be **audit-logged** (who reset whose password, when) since it
  lets a privileged actor take over another user's credential reset — a
  capability that doesn't exist for the self-service `/auth/forgot-password`
  path today.
- Self-service forgot-password with **no admin present at all** (e.g. a
  single self-signed-up user with no tenant admin) has the same problem as
  Flow 2 §4 and the same two options: scope it out, or add a second factor
  (SMS/backup codes) later.

## 6. Cross-cutting questions worth settling before building anything

1. **Who actually needs this — SaaS-hosted adopters, or adopters running
   their own instance?** If we (the platform team) host the DB/logs, ops
   already has the runbook fallback today; the API-shaped fixes below are
   about *self-serviceability*, not unblocking anyone technically. If
   adopters self-host, they have no DB/log access to their own instance
   unless we explicitly give it to them — which makes the API-return-token
   fixes in §3 mandatory rather than a nice-to-have.
2. **Is anonymous self-signup (`/auth/register` with no `tenant_id`) a real
   product path, or legacy/demo-only?** Determines whether §4 needs
   anything beyond "scope it out."
3. **Do we want an explicit per-tenant "no email delivery" flag** (vs.
   silently having every resend/setup path return the token in the
   response always)? A flag would let the UI only show a "copy setup link"
   affordance for tenants that need it, keeping the normal flow's UX
   (clean "check your email" message) unchanged for tenants that do have
   SMTP. Recommend deferring this — always returning the token to an
   already-privileged caller is safe (§3.2's trust-boundary argument) and
   is simpler to ship; a flag can be layered on later purely for UX.

## 7. Recommended plan

| Phase | Change | Effort | Unblocks |
|---|---|---|---|
| **0** | Return `setup_token` from `POST /auth/tenants` (new `TenantCreateResponse`) | Small — 1 schema, 1 route change | The exact reported blocker; full API-only tenant-onboard-and-activate flow |
| **0** | Return the re-minted token from both `resend-setup-link` endpoints (self-service + tenant-user), alongside the existing "email sent" message | Small | Recovery when a link expires/is lost and email still isn't wired up |
| **1** | Confirm with product whether plain self-signup is a real path (§6.2) | None — decision only | Scopes whether Flow 2 needs any engineering at all |
| **1** | Admin-initiated password reset that returns the `RESET` token to the calling admin, audit-logged | Medium — new endpoint, permission check, audit entry | Locked-out users under SMTP-less tenants |
| **2** *(only if §6.2 says yes)* | Second ownership-proof channel for self-signup (SMS OTP or manual approval queue) | Large — new provider/UI | Anonymous self-signup without email |
| **later** | Frontend: "Copy setup link" affordance on tenant/tenant-user creation and resend screens, surfaced whenever the API returns a token | Small–Medium, frontend-only | Turns the API fix into something a non-technical adopter admin can actually use |

Phase 0 is the one that directly answers the original question — **yes, the
full create-tenant-and-activate-it flow can be done purely over the API
today, except for this one missing field** — and it ships without loosening
any of the existing tenant-activation safety checks (§3.1). It also comes
with the caveat from §3.2.1: what it delivers is a link a trusted admin can
relay manually, not automated delivery to the tenant's contact person — the
per-tenant flag in §6.3 is the natural next step if that manual step needs
to become a supported, permanent workflow rather than a stopgap.

## 8. Feasibility check: "fetch the token via a DB query" as a fallback

A separate internal suggestion was to lean on "the API, plus a DB query" for
the set-password case, without going into exactly how the two would fit
together. That's ambiguous as stated, but it collapses into two concrete,
checkable readings once you go to the schema. Short answer first: **yes,
it's possible — but only in a narrower and more fragile way than "run a
query and get the token" suggests, for reasons that are specific to how
this table is built, not a hypothetical concern.**

### 8.1 What's actually in the table

```
token_verification
  id            serial primary key
  token         text, unique      -- the full signed JWT string
  is_active     boolean
  expires_at    timestamptz
  created_at    timestamptz
  created_by    uuid              -- the user's id (not a declared FK)
  updated_at    timestamptz
  updated_by    uuid
```

([`models/verification.py`](../services/auth-service/app/models/verification.py))

Two things this table deliberately does **not** store, per the repository's
own header comment
([`verification_repository.py:1-8`](../services/auth-service/app/repositories/verification_repository.py)):

- **Which user it belongs to, as a joinable identity** — `created_by` is a
  bare UUID column with no foreign key. It happens to hold the user's id,
  but the schema itself doesn't declare that relationship.
- **What kind of token it is** (`SETUP` vs `VERIFY` vs `RESET`). That's
  embedded as a `type` claim *inside the signed JWT payload*, not a column
  on the row. The one place this repo needs to filter by type
  (`deactivate_all_for_user`) does it by decoding every candidate JWT with
  the service's RS256 public key and reading `payload["type"]` — there is
  no `WHERE token_type = 'SETUP'` available to plain SQL.

### 8.2 Reading 1 — a human runs SQL directly (what the existing runbook already does)

This is fully possible today and is exactly the DB fallback already
documented in the onboarding runbook:

```sql
-- 1. Resolve the user's id (need this first — created_by has no join to go the other way)
SELECT id FROM users WHERE email = '<tenant-admin-email>';

-- 2. Fetch their most recent active token
SELECT token FROM token_verification
WHERE created_by = '<user_id_from_step_1>' AND is_active = true
ORDER BY created_at DESC LIMIT 1;
```

That "most recent active row" heuristic is standing in for a real type
filter, and it only works because of an invariant enforced elsewhere in the
*application*, not by this query: a not-yet-activated user (no credentials
row yet) can only ever have a `SETUP` **or** `VERIFY` token outstanding,
never both, and can never also have a `RESET` token — `request_password_reset`
explicitly refuses to issue one unless the user `is_active` **and** already
has credentials
([`auth_service.py:324-330`](../services/auth-service/app/services/auth_service.py)).
So for the specific pre-activation case this is being proposed for, "the
newest active row for this user" and "the SETUP token" happen to be the same
row — but the query has no idea that's true; it's true by coincidence of
how the rest of the code behaves today. Reuse this same query for a
different case (e.g. "give me the active RESET token" once §5's
admin-initiated reset exists, for a user who might also have a stale SETUP
row) and the coincidence breaks — you'd get whichever row is newest, not
necessarily the right type.

**Feasible, but only correct within the specific case it's being proposed
for, and silently wrong outside it.** It also requires giving whoever does
this direct production DB read access, and means a live, bearer-equivalent
JWT (the exact string a browser would use to set a password) ends up
pasted into a terminal / query tool / person's clipboard — outside any
audit trail the API layer would otherwise produce.

### 8.3 Reading 2 — an API endpoint does the equivalent lookup server-side

If instead the intent is a proper endpoint — "given a user, look up their
current active setup/reset token and hand it back" — that's also feasible,
and is strictly better than 8.2: the *application* already has the RS256
key material and the decode logic to filter by type correctly
(`deactivate_all_for_user`'s own approach), so it can answer "which token
is actually the SETUP one" precisely, instead of relying on the
newest-row coincidence. Concretely this is just:

```python
rows = await verification_repo.get_active_for_user(user_id)  # created_by = user_id, is_active = true
setup_row = next(r for r in rows if decode(r.token)["type"] == "setup" and not_expired(r))
```

...gated behind the same admin/tenant-admin permission checks every other
tenant-user endpoint already uses. **This is not a different idea from
Phase 0 in §7 — it's the same fix, arrived at from "query the DB for the
token" instead of "don't throw the token away in the first place."** Phase
0 is simpler because the token is already sitting in a local variable at
creation time (`provision_user` returns it) — there's no need to write a
new lookup at all for the create-tenant/create-user paths specifically.
Where a real lookup-by-user *is* needed is exactly the resend/reissue paths
in §3.3 and the admin-initiated reset in §5 (cases where the token wasn't
just minted in the current request) — and those should be built this way
(reusing the app's own decode logic), not as raw SQL.

### 8.4 Bottom line

| | Reading 1: raw SQL | Reading 2: an endpoint |
|---|---|---|
| Possible today? | Yes, no code changes | Yes, small addition (§3.3 / §5 already propose it) |
| Correctly identifies token *type*? | No — relies on a coincidence that holds today, not a real filter | Yes — reuses the app's own JWT decode |
| Requires prod DB credentials for whoever onboards tenants? | Yes | No |
| Audit trail? | None | Whatever the endpoint's own logging/permission layer provides |
| Recommendation | Fine as a stopgap for the exact pre-activation case, same as today's runbook | The right place to land this once it needs to be a supported (not ad hoc) fallback |

So: the instinct to reach for "just query the DB" isn't wrong — it's what
the org already does today per the existing runbook, and it does work for
the one case (pre-activation setup) it's being proposed for. It doesn't
generalize to "any token, any user" the way a plain sentence like "use the
API and a DB query" implies, because the table was deliberately built
without a type column — that filtering only ever existed inside the
application's own JWT-decoding code. Anywhere this needs to become a
repeatable, safe process rather than an occasional ops query, it should be
the API-endpoint version (8.3), which is exactly what §7's Phase 0/1 rows
already build.
