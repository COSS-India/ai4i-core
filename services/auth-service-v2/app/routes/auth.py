"""
Authentication routes: register, login, logout, refresh, password management.
"""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Body, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.config import settings
from app.core.responses import success_response
from app.core.database import get_db
from app.dependencies.auth import get_current_active_user
from app.dependencies.permissions import require_any_role
from app.dependencies.services import get_auth_service, get_cache_service
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.schemas.auth import (
    InternalProvisionUserRequest,
    InternalProvisionUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    PasswordChangeRequest,
    RegisterRequest,
    ResendSetupLinkRequest,
    SetPasswordRequest,
    TokenRefreshRequest,
    TokenRefreshResponse,
)
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService
from app.services.session_service import SessionService
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_context(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.headers.get(
        "X-Forwarded-For",
        request.client.host if request.client else None,
    )
    user_agent = request.headers.get("User-Agent")
    return ip_address, user_agent


def _build_set_password_page(token: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Set Password</title>
    <style>
      :root {{
        color-scheme: light dark;
      }}
      body {{
        margin: 0;
        font-family: Arial, sans-serif;
        background: #0f172a;
        color: #e2e8f0;
      }}
      .container {{
        max-width: 460px;
        margin: 48px auto;
        background: #111827;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 16px 0;
        font-size: 24px;
      }}
      .field {{
        margin-bottom: 14px;
      }}
      label {{
        display: block;
        margin-bottom: 8px;
        color: #cbd5e1;
      }}
      input {{
        width: 100%;
        box-sizing: border-box;
        background: #0b1220;
        border: 1px solid #475569;
        color: #e2e8f0;
        border-radius: 8px;
        padding: 10px 12px;
      }}
      button {{
        width: 100%;
        background: #2563eb;
        border: none;
        color: #ffffff;
        border-radius: 8px;
        padding: 11px 14px;
        font-weight: 600;
        cursor: pointer;
      }}
      button:disabled {{
        cursor: not-allowed;
        opacity: 0.7;
      }}
      .error {{
        color: #fca5a5;
        margin-top: 10px;
        white-space: pre-line;
      }}
      .success {{
        color: #86efac;
        margin-top: 10px;
      }}
      ul {{
        margin: 10px 0 16px 20px;
        padding: 0;
        color: #cbd5e1;
      }}
      .ok {{
        color: #86efac;
      }}
      .hint {{
        font-size: 12px;
        color: #94a3b8;
        margin-top: 8px;
      }}
    </style>
  </head>
  <body>
    <main class="container">
      <h1>Set your password</h1>
      <p class="hint">Use a strong password to finish account setup.</p>
      <form id="setPasswordForm">
        <input type="hidden" id="token" value="{token}" />
        <div class="field">
          <label for="new_password">New Password</label>
          <input type="password" id="new_password" name="new_password" autocomplete="new-password" required />
        </div>
        <div class="field">
          <label for="confirm_password">Confirm Password</label>
          <input type="password" id="confirm_password" name="confirm_password" autocomplete="new-password" required />
        </div>
        <ul id="rules">
          <li id="r-len">At least 8 characters</li>
          <li id="r-upper">At least one uppercase letter</li>
          <li id="r-lower">At least one lowercase letter</li>
          <li id="r-digit">At least one number</li>
          <li id="r-special">At least one special character</li>
          <li id="r-match">Passwords match</li>
        </ul>
        <button id="submitBtn" type="submit">Set Password</button>
      </form>
      <div id="status" aria-live="polite"></div>
    </main>
    <script>
      const form = document.getElementById("setPasswordForm");
      const submitBtn = document.getElementById("submitBtn");
      const status = document.getElementById("status");
      const newPasswordEl = document.getElementById("new_password");
      const confirmPasswordEl = document.getElementById("confirm_password");
      const tokenEl = document.getElementById("token");

      const checks = {{
        len: (v) => v.length >= 8,
        upper: (v) => /[A-Z]/.test(v),
        lower: (v) => /[a-z]/.test(v),
        digit: (v) => /[0-9]/.test(v),
        special: (v) => /[!@#$%^&*()_+\\-=[\\]{{}}|;:,.<>?]/.test(v),
        match: (v, c) => v.length > 0 && v === c,
      }};

      const ruleMap = {{
        len: "r-len",
        upper: "r-upper",
        lower: "r-lower",
        digit: "r-digit",
        special: "r-special",
        match: "r-match",
      }};

      function setRuleState(ruleKey, ok) {{
        const el = document.getElementById(ruleMap[ruleKey]);
        if (!el) return;
        el.classList.toggle("ok", ok);
      }}

      function validateAll() {{
        const p = newPasswordEl.value || "";
        const c = confirmPasswordEl.value || "";
        const result = {{
          len: checks.len(p),
          upper: checks.upper(p),
          lower: checks.lower(p),
          digit: checks.digit(p),
          special: checks.special(p),
          match: checks.match(p, c),
        }};
        Object.keys(result).forEach((k) => setRuleState(k, result[k]));
        return Object.values(result).every(Boolean);
      }}

      newPasswordEl.addEventListener("input", validateAll);
      confirmPasswordEl.addEventListener("input", validateAll);
      validateAll();

      form.addEventListener("submit", async (event) => {{
        event.preventDefault();
        status.className = "error";
        status.textContent = "";

        if (!validateAll()) {{
          status.textContent = "Please fix password validation errors before continuing.";
          return;
        }}

        const payload = {{
          token: tokenEl.value,
          new_password: newPasswordEl.value,
          confirm_password: confirmPasswordEl.value,
        }};

        submitBtn.disabled = true;
        submitBtn.textContent = "Setting password...";

        try {{
          const response = await fetch(window.location.pathname, {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
            }},
            body: JSON.stringify(payload),
          }});

          const data = await response.json().catch(() => ({{}}));
          if (!response.ok) {{
            const message = data?.detail?.message || data?.detail || data?.message || "Failed to set password.";
            throw new Error(typeof message === "string" ? message : JSON.stringify(message));
          }}

          status.className = "success";
          status.textContent = "Password setup successfully. You can now login from the portal.";
          form.reset();
          validateAll();
        }} catch (err) {{
          status.className = "error";
          status.textContent = err?.message || "Failed to set password.";
        }} finally {{
          submitBtn.disabled = false;
          submitBtn.textContent = "Set Password";
        }}
      }});
    </script>
  </body>
</html>"""


@router.post("/register")
async def register(
    body: RegisterRequest,
    svc: AuthService = Depends(get_auth_service),
):
    user = await svc.register(
        email=body.email,
        username=body.username,
        password=body.password,
        confirm_password=body.confirm_password,
        full_name=body.full_name,
        phone_number=body.phone_number,
        tz=body.timezone,
        language=body.language,
        tenant_id=body.tenant_id,
        is_tenant=body.is_tenant,
    )
    return success_response(data={
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "message": "User registered successfully.",
    })


@router.get("/set-password", response_class=HTMLResponse)
async def set_password_page(
    token: str | None = Query(default=None, alias="token"),
):
    if not token:
        return HTMLResponse(
            content="<html><body><h3>Invalid setup link.</h3><p>Missing token.</p></body></html>",
            status_code=400,
        )
    return HTMLResponse(content=_build_set_password_page(token), status_code=200)


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    svc: AuthService = Depends(get_auth_service),
):
    ip_address, user_agent = _client_context(request)
    return await svc.login(
        email=body.email,
        password=body.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.post("/guest/login", response_model=LoginResponse)
async def guest_login(
    request: Request,
    svc: AuthService = Depends(get_auth_service),
):
    email = (settings.guest_email or "").strip()
    password = settings.guest_password
    if not email or not password:
        raise HTTPException(
            status_code=503,
            detail="Guest login is not configured.",
        )
    ip_address, user_agent = _client_context(request)
    return await svc.login(
        email=email,
        password=password,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    body: TokenRefreshRequest,
    svc: AuthService = Depends(get_auth_service),
):
    return await svc.refresh_token(body.refresh_token)


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    current_user: User = Depends(get_current_active_user),
    svc: AuthService = Depends(get_auth_service),
):
    await svc.logout(user_id=current_user.id, refresh_token_str=body.refresh_token)
    return LogoutResponse(message="Logged out successfully.", logged_out=True)


@router.post("/change-password")
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    svc: AuthService = Depends(get_auth_service),
):
    await svc.change_password(
        user=current_user,
        current_password=body.current_password,
        new_password=body.new_password,
        confirm_password=body.confirm_password,
    )
    return success_response(data={"message": "Password changed successfully."})


@router.post(
    "/internal/provision-user",
    include_in_schema=False,
    response_model=InternalProvisionUserResponse,
)
async def provision_user_internal(
    body: InternalProvisionUserRequest,
    svc: AuthService = Depends(get_auth_service),
):
    return await svc.provision_user(
        email=body.email,
        username=body.username,
        full_name=body.full_name,
        phone_number=body.phone_number,
        tenant_id=body.tenant_id,
        is_tenant=body.is_tenant,
    )


@router.post("/set-password")
async def set_password(
    body: SetPasswordRequest | None = Body(default=None),
    token_query: str | None = Query(default=None, alias="token"),
    svc: AuthService = Depends(get_auth_service),
):
    token = (body.token if body else None) or token_query
    new_password = body.new_password if body else None
    confirm_password = body.confirm_password if body else None

    if not token or not new_password or not confirm_password:
        raise HTTPException(
            status_code=422,
            detail="token, new_password, and confirm_password are required in JSON body",
        )

    await svc.set_password_with_setup_token(
        token=token,
        new_password=new_password,
        confirm_password=confirm_password,
    )
    return success_response(data={"message": "Password set successfully."})


@router.post("/resend-setup-link")
async def resend_setup_link(
    body: ResendSetupLinkRequest,
    svc: AuthService = Depends(get_auth_service),
):
    setup_token = await svc.resend_setup_link(email=body.email)
    return success_response(data={"setup_token": setup_token})


@router.post("/sessions/revoke-by-tenant/{tenant_id}")
async def revoke_sessions_by_tenant(
    request: Request,
    tenant_id: str = Path(
        ...,
        min_length=1,
        max_length=100,
        pattern=r".*\S.*",
        description="Tenant identifier",
    ),
    current_admin: User = Depends(require_any_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """
    Admin-only endpoint to invalidate all active sessions for users in a tenant.
    Used by multi-tenant service when tenant is suspended/deactivated.
    """
    mt_factory = getattr(request.app.state, "multi_tenant_session_factory", None)
    if not mt_factory:
        raise HTTPException(status_code=503, detail="Multi-tenant DB not configured in auth service")

    cooldown_scope = f"tenant:{tenant_id}"
    acquired = await cache.acquire_revocation_cooldown(
        cooldown_scope,
        settings.revocation_endpoint_cooldown_seconds,
    )
    if not acquired:
        retry_after = await cache.get_revocation_cooldown_ttl(cooldown_scope)
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Session revocation for this tenant was requested too recently.",
                "retry_after_seconds": retry_after,
                "tenant_id": tenant_id,
                "requested_by": current_admin.id,
            },
        )

    tenant_service = TenantService(mt_factory, cache)
    user_ids = await tenant_service.get_tenant_user_ids(tenant_id) or []
    if not user_ids:
        return success_response(data={
            "tenant_id": tenant_id,
            "users_matched": 0,
            "sessions_revoked": 0,
        })

    session_service = SessionService(SessionRepository(db), cache)
    sessions_revoked = await session_service.invalidate_all_for_users(user_ids)
    await session_service.commit()
    await cache.delete_tenant_status(tenant_id)

    return success_response(data={
        "tenant_id": tenant_id,
        "users_matched": len(user_ids),
        "sessions_revoked": sessions_revoked,
    })


class RevokeSessionsByUsersRequest(BaseModel):
    user_ids: list[int]


@router.post("/sessions/revoke-by-users")
async def revoke_sessions_by_users(
    body: RevokeSessionsByUsersRequest,
    current_admin: User = Depends(require_any_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
):
    """
    Admin-only endpoint to invalidate all active sessions for a set of users.
    Useful for external orchestrators that already know impacted user IDs.
    """
    user_ids = sorted({int(uid) for uid in body.user_ids if uid is not None})
    if not user_ids:
        return success_response(data={"users_matched": 0, "sessions_revoked": 0})

    user_scope_hash = hashlib.sha256(",".join(map(str, user_ids)).encode("utf-8")).hexdigest()[:16]
    cooldown_scope = f"users:{user_scope_hash}"
    acquired = await cache.acquire_revocation_cooldown(
        cooldown_scope,
        settings.revocation_endpoint_cooldown_seconds,
    )
    if not acquired:
        retry_after = await cache.get_revocation_cooldown_ttl(cooldown_scope)
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Session revocation for this user set was requested too recently.",
                "retry_after_seconds": retry_after,
                "users_matched": len(user_ids),
                "requested_by": current_admin.id,
            },
        )

    session_service = SessionService(SessionRepository(db), cache)
    sessions_revoked = await session_service.invalidate_all_for_users(user_ids)
    await session_service.commit()
    tenant_ids_result = await db.execute(
        select(User.tenant_id_cached)
        .where(User.id.in_(user_ids), User.tenant_id_cached.is_not(None))
        .distinct()
    )
    tenant_ids = [row[0] for row in tenant_ids_result.fetchall() if row[0]]
    for tenant_id in tenant_ids:
        await cache.delete_tenant_status(tenant_id)

    return success_response(data={
        "users_matched": len(user_ids),
        "sessions_revoked": sessions_revoked,
    })
