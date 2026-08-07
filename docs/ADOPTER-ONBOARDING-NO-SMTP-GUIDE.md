# Onboarding a New Adopter Without Email/SMTP — Step-by-Step Guide

**Audience:** Platform/Adopter Admin onboarding a tenant whose environment has
no working SMTP yet.
**Requires:** Platform admin UI access **+** read access to the platform
Postgres DB (to fetch the setup token that would otherwise be emailed).
**Why this is needed:** Tenant admins are created passwordless — the normal
flow emails them a "Set Your Password" link. With no SMTP, that email never
arrives, so the token has to be pulled from the DB and used directly.

---

## Step 1 — Create the tenant

**UI:** *Tenant Management → Create Tenant*

| Field | Value |
|---|---|
| Organisation | Adopter's org name |
| Contact Name | Tenant admin's name |
| Email | Tenant admin's login email |
| Phone Number | *(optional)* |

Submit. The tenant is created in `PENDING` status with an inactive tenant-admin
user. The system will *try* to email a setup link to that address — it won't
arrive (no SMTP), which is expected. Continue to Step 2.

---

## Step 2 — Look up the tenant admin's user ID

```sql
SELECT id, email, tenant_id
FROM users
WHERE email = '<tenant-admin-email-from-step-1>'
ORDER BY created_at DESC
LIMIT 1;
```

Copy the `id` (a UUID) — this is the user's `created_by` value used next.

---

## Step 3 — Fetch the setup token for that user

```sql
SELECT token, expires_at
FROM token_verification
WHERE created_by = '<user-id-from-step-2>'
  AND is_active = true
ORDER BY created_at DESC
LIMIT 1;
```

This is the same token that would have been embedded in the emailed
"Set Your Password" link. It's a single-use JWT, valid for 48 hours from
creation — check `expires_at`. If it has expired, use the UI's
**Resend setup link** action for that tenant/user, then re-run this query.

---

## Step 4 — Set the tenant admin's password via API

```
POST /auth/set-password
Content-Type: application/json

{
  "token": "<token-from-step-3>",
  "new_password": "<TemporaryPassw0rd!>",
  "confirm_password": "<TemporaryPassw0rd!>"
}
```

Response: `{ "success": true, "data": { "message": "Password set. You can now log in." } }`

This also flips the tenant from `PENDING` → `ACTIVE`.

---

## Step 5 — Share the credentials with the adopter

Send the tenant admin's **email** and the **password you just set** to the
adopter through whichever channel you already use to reach them (phone,
chat, a different working email, in person). Ask them to change the
password after first login.

---

## Step 6 — Create a Tier for this adopter

**UI:** *Tier Management → Create Tier*

Set quotas, rate limits, cost, and map the services this adopter is allowed
to use. Save.

> A Tier can only be assigned to a tenant once it has at least one service
> mapped to it — do that here first if this is a brand-new Tier.

---

## Step 7 — Map the Tier to the tenant

**UI:** *Tenant Management → (find the tenant) → Assign Tier*

Select the Tier created in Step 6, set budget / effective dates if
required, and save.

---

## Step 8 — Tenant admin logs in

Tenant admin signs in with the credentials from Step 5, and should change
their password immediately (*Profile → Change Password*).

---

## Step 9 — Tenant admin creates an API key

**UI:** *API Key Management → Create API Key*

Name the key and save. **Copy the key value immediately — it is shown only
once.**

---

## Step 10 — Use the API key for inference

```
POST <gateway-host>/api/v1/<service-path>
X-API-Key: <key-from-step-9>
Content-Type: application/json

{ ...request body for the specific service... }
```

---

## Notes

- Steps 2–4 require production DB read access — they're a manual ops
  workaround for the missing email channel, not something the adopter does
  themselves.
- Every additional tenant user created later goes through the same
  Steps 2–4 (look up their `id`, fetch their token, set their password)
  until SMTP is configured for this tenant.
- Once SMTP is configured for the adopter, all of this reverts to the
  normal self-service email flow — no further manual steps needed.
