# Creating a Tenant User Without Email/SMTP — Step-by-Step Guide

**Audience:** Either the **Platform/Adopter Admin**, or the tenant's own
**Tenant Admin** — both can add users to a tenant; the only difference is
which JWT you authenticate with and whether `tenant_id` is explicit.
**Requires:** API access (Postman/curl) is enough on its own for this flow —
DB read access is only needed as a fallback if the user is created through
the Portal UI instead of the API (see Step 1, note below).
**Prerequisite:** The tenant itself must already be `ACTIVE`.
Tenant users cannot be added while the tenant is still `PENDING`.

---

## Who can do this

| Caller | `tenant_id` | Scope |
|---|---|---|
| Platform Admin | pass explicitly | Any tenant |
| Tenant Admin | implicit (their own) | Only their own tenant |

---

## Step 1 — Create the tenant user via API

Unlike tenant creation, **this endpoint returns the setup token directly in
its response** — no DB query needed if you call it this way.

```
POST /auth/tenants/{tenant_id}/users
Authorization: Bearer <caller-JWT>      (platform admin OR that tenant's own TENANT_ADMIN)
Content-Type: application/json

{
  "email": "newuser@example.com",
  "full_name": "New User",
  "phone_number": "+91XXXXXXXXXX",   // optional
  "role": "USER"                      // or "TENANT ADMIN"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "user_id": "...",
    "setup_token": "<jwt>",
    "message": "Tenant user provisioned. Share the setup link to complete onboarding."
  }
}
```

Copy `setup_token` straight from this response and skip to Step 2.

> **If the user was instead created through the Portal UI**
> (*Tenant Management → Add Tenant User*): that form calls this same
> endpoint, but today it discards `setup_token` from the response and only
> shows a generic "User provisioned" toast — it does not surface the token
> anywhere. If that's how the user was created, fall back to a DB lookup:
>
> ```sql
> -- 1a. Get the new user's id
> SELECT id FROM users
> WHERE email = '<newuser-email>'
> ORDER BY created_at DESC
> LIMIT 1;
>
> -- 1b. Get their active setup token
> SELECT token, expires_at FROM token_verification
> WHERE created_by = '<id-from-1a>' AND is_active = true
> ORDER BY created_at DESC
> LIMIT 1;
> ```

---

## Step 2 — Set the user's password via API

```
POST /auth/set-password
Content-Type: application/json

{
  "token": "<setup_token-from-step-1>",
  "new_password": "<TemporaryPassw0rd!>",
  "confirm_password": "<TemporaryPassw0rd!>"
}
```

This creates their credentials and activates the account. (Token is
single-use, 48-hour expiry — if it's gone stale, trigger
`POST /auth/tenants/{tenant_id}/users/{user_id}/resend-setup-link`, then
repeat Step 1's DB lookup to get the freshly-minted token — that endpoint
also only emails it, it doesn't return it in the response.)

---

## Step 3 — Share the credentials with the user

Send their email and the password you just set through whatever channel
you already use to reach them (phone, chat, etc.).

---

## Step 4 — Tier: nothing to do

Tiers are assigned at the **tenant** level, not per-user. Every user
created under this tenant automatically inherits the tenant's
already-assigned Tier/quota — there's no per-user Tier step to repeat.

---

## Step 5 — User logs in

The new user signs in with the credentials from Step 3. They can change
their password afterwards via *Profile → Change Password*.

---

## Step 6 — User creates their own API key

**UI:** *API Key Management → Create API Key* — name it, pick permissions,
save, and copy the key value (**shown only once**).

Any authenticated tenant user — `USER` or `TENANT ADMIN` role — can create
their own key; it's not restricted to admins. Equivalent API call:

```
POST /auth/api-keys
Authorization: Bearer <user-JWT>
Content-Type: application/json

{
  "key_name": "my-key",
  "permissions": ["nmt.inference"],
  "expires_days": 90
}
```

---

## Step 7 — Use the API key for inference

```
POST <gateway-host>/api/v1/<service-path>
X-API-Key: <key-from-step-6>
Content-Type: application/json

{ ...request body for the specific service... }
```

---

## Notes

- The API path (Step 1) is simpler than tenant creation itself: the token
  is handed back in the same response, so no DB access is required at all
  if onboarding is done via API end-to-end.
- DB access is only needed as a fallback for users created through the
  Portal UI (which currently swallows the token) or when a link expires
  and needs resending.
- Once SMTP is configured for the tenant, this reverts to normal — create
  the user any way you like and let the emailed link do the rest.
