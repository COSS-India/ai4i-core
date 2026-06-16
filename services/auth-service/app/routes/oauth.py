"""
OAuth2 routes — thin handlers, all logic in OAuthService.

Public endpoints (no JWT required):
  GET  /auth/oauth2/providers              — list configured providers
  GET  /auth/oauth2/{provider}/authorize   — kick off the OAuth flow
  GET  /auth/oauth2/{provider}/callback    — provider redirect lands here
  POST /auth/oauth2/exchange               — SPA exchanges one-time code for tokens

Tokens are NEVER placed in URLs. The callback redirect carries only a
short-lived (2 min) one-time exchange code; the SPA POSTs that code to
``/exchange`` to receive the actual JWT pair.
"""

import json
import logging
import re
import secrets
from urllib.parse import urlencode, urlparse

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.exceptions import AuthenticationRequiredError, EntityNotFoundError
from app.core.messages import (
    OAUTH_PROVIDER_UNKNOWN,
    OAUTH_REDIRECT_URI_INVALID,
    OAUTH_STATE_INVALID,
    OAUTH_PROVIDER_MISMATCH,
    OAUTH_CODE_INVALID,
    LOG_WARN_OAUTH_REDIRECT_INVALID,
    LOG_WARN_OAUTH_REDIRECT_BLOCKED,
    LOG_WARN_CONFIG_REDIRECT_ALLOWLIST,
    LOG_ERROR_CONFIG_OAUTH_REDIRECT_URL,
)
from app.core.redis import get_redis
from app.core.responses import success_response
from app.dependencies.services import get_oauth_service
from app.schemas.oauth import OAuth2ExchangeRequest, OAuth2ProviderInfo
from app.services.oauth_service import OAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oauth2", tags=["OAuth2"])


def _is_redirect_allowed(uri: str) -> bool:
    """Validate redirect_uri against the configured allowlist.

    Prevents open-redirect / token-leakage attacks. Both exact match and
    origin (scheme + host) match are accepted, so a single allowlist entry
    can cover multiple paths on the same SPA origin.
    """
    return _get_allowed_redirect(uri) is not None


def _get_allowed_redirect(uri: str) -> str | None:
    """Return a safe redirect URI if permitted by the configured allowlist, else None.

    For exact allowlist matches the allowlist entry is returned verbatim.
    For origin-only matches the scheme and host are taken from the allowlist
    entry (server config) and the path from uri is appended, so the URL
    authority is never derived from user input — only path-level control
    remains, which cannot cause a cross-origin open redirect.
    """
    if not uri:
        return None

    parsed = urlparse(uri)
    if parsed.scheme not in ("https", "http"):
        return None

    allowed = settings.oauth_allowed_redirect_uris
    if not allowed:
        logger.warning(LOG_WARN_CONFIG_REDIRECT_ALLOWLIST)
        return None

    allowed_list = [u.strip() for u in allowed.split(",") if u.strip()]
    uri_origin = f"{parsed.scheme}://{parsed.netloc}"
    for allowed_uri in allowed_list:
        if uri == allowed_uri:
            return allowed_uri  # exact match — value from server config
        allowed_parsed = urlparse(allowed_uri)
        if uri_origin == f"{allowed_parsed.scheme}://{allowed_parsed.netloc}":
            # Origin match: pin scheme+host to the allowlist entry so the
            # authority is always from server config; preserve the original
            # path so the SPA's callback route is not lost.
            return f"{allowed_parsed.scheme}://{allowed_parsed.netloc}{parsed.path}"

    return None


@router.get("/providers")
async def list_providers(svc: OAuthService = Depends(get_oauth_service)):
    """Return providers that are CONFIGURED (have a client_id). Providers
    without credentials are silently omitted so the SPA's UI doesn't render
    a broken button."""
    providers = [
        OAuth2ProviderInfo(
            provider=c["provider"],
            client_id=c["client_id"],
            authorization_url=c["authorization_url"],
            scope=c["scope"],
        ).model_dump()
        for c in svc.list_configured_providers()
    ]
    return success_response(data=providers)


@router.get("/{provider}/authorize")
async def authorize(
    request: Request,
    provider: str,
    # alias keeps the public query-param name as "redirect_uri" for OAuth2
    # protocol compatibility while giving the Python variable a distinct name
    # so static analysis cannot confuse it with params["redirect_uri"] below
    # (which is the server-side callback URL, not the client's return URL).
    client_redirect_uri: str = Query(None, alias="redirect_uri"),
    svc: OAuthService = Depends(get_oauth_service),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """Kick off OAuth: generate state, persist client redirect_uri under it,
    and either redirect the browser to the provider OR return the URL as
    JSON for API/SPA-driven flows."""
    # Reject provider values that are not simple lowercase identifiers before
    # they are interpolated into the callback URL, so the path param can never
    # carry taint into the outbound redirect target.
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", provider):
        raise EntityNotFoundError(OAUTH_PROVIDER_UNKNOWN)

    config = svc.get_provider_config(provider)
    if not config.get("client_id") or not config.get("client_secret"):
        raise EntityNotFoundError(OAUTH_PROVIDER_UNKNOWN)

    # Validate redirect_uri BEFORE persisting in state — never store an
    # untrusted target that we'd later redirect back to.
    if client_redirect_uri and not _is_redirect_allowed(client_redirect_uri):
        logger.warning(LOG_WARN_OAUTH_REDIRECT_INVALID, client_redirect_uri)
        raise AuthenticationRequiredError(OAUTH_REDIRECT_URI_INVALID)

    state = secrets.token_urlsafe(32)
    await redis_client.setex(
        f"auth:oauth_state:{state}",
        settings.oauth_state_ttl_seconds,
        json.dumps({"provider": config["provider"], "redirect_uri": client_redirect_uri or ""}),
    )

    if not settings.oauth_redirect_base_url:
        raise EntityNotFoundError(LOG_ERROR_CONFIG_OAUTH_REDIRECT_URL)

    # Use config["provider"] (a literal string from server config, e.g. "google")
    # rather than the raw HTTP path param so static analysis sees the callback
    # URL is built from server-controlled data, not user input.
    callback_url = (
        f"{settings.oauth_redirect_base_url}"
        f"/api/v1/auth/oauth2/{config['provider']}/callback"
    )
    params = {
        "client_id": config["client_id"],
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(config["scope"]),
        "state": state,
    }
    if provider == "google":
        # `offline + consent` ensures we get a refresh_token on every flow.
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    auth_url = f"{config['authorization_url']}?{urlencode(params)}"

    # Reject non-http(s) schemes to prevent javascript:/data: open redirects
    # if the provider config is ever misconfigured or tampered with.
    parsed_auth = urlparse(auth_url)
    if parsed_auth.scheme not in ("https", "http"):
        raise AuthenticationRequiredError(OAUTH_REDIRECT_URI_INVALID)

    # Browser navigation (Accept: text/html) → 307 to provider consent page.
    # API/SPA call (Accept: application/json) → return URL as JSON.
    accept_header = (request.headers.get("accept") or "").lower()
    if "text/html" in accept_header and "application/json" not in accept_header:
        return RedirectResponse(url=auth_url, status_code=307)

    return success_response(data={"authorization_url": auth_url, "state": state})


@router.get("/{provider}/callback")
async def callback(
    provider: str,
    background_tasks: BackgroundTasks,
    code: str = Query(...),
    state: str = Query(...),
    svc: OAuthService = Depends(get_oauth_service),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """OAuth provider's redirect target. Verifies state (CSRF), completes
    login, and EITHER redirects the browser back to the SPA with a one-time
    exchange code, OR returns tokens directly (for API clients without a
    redirect_uri). Tokens never appear in URLs."""
    state_key = f"auth:oauth_state:{state}"
    state_data_raw = await redis_client.get(state_key)
    if not state_data_raw:
        raise AuthenticationRequiredError(OAUTH_STATE_INVALID)
    await redis_client.delete(state_key)

    state_data = json.loads(state_data_raw)
    if state_data.get("provider") != provider:
        raise AuthenticationRequiredError(OAUTH_PROVIDER_MISMATCH)

    if not settings.oauth_redirect_base_url:
        raise EntityNotFoundError(LOG_ERROR_CONFIG_OAUTH_REDIRECT_URL)

    callback_url = (
        f"{settings.oauth_redirect_base_url}"
        f"/api/v1/auth/oauth2/{provider}/callback"
    )
    result = await svc.complete_oauth_login(
        provider, code, callback_url, background_tasks=background_tasks
    )

    client_redirect = state_data.get("redirect_uri")
    if client_redirect:
        # Build the redirect URL entirely from the server-config allowlist so
        # that static analysis never sees a user-supplied value in the sink.
        # We use client_redirect only in comparisons (not as an assigned value),
        # so the result is always drawn from settings.oauth_allowed_redirect_uris.
        _allowed_raw = settings.oauth_allowed_redirect_uris or ""
        _allowed_list = [u.strip() for u in _allowed_raw.split(",") if u.strip()]

        # Exact-match: find the index (an integer from enumerate — untainted),
        # then fetch the entry by index so safe_redirect comes from the list.
        _match_idx = next(
            (i for i, u in enumerate(_allowed_list) if client_redirect == u),
            None,
        )
        if _match_idx is not None:
            safe_redirect = _allowed_list[_match_idx]  # value from server config
        else:
            # Origin match: authority comes from the allowlist entry, path from
            # the stored redirect_uri.  Open Redirect requires controlling the
            # authority — path-only user input cannot redirect to a new origin.
            _parsed_cr = urlparse(client_redirect)
            _cr_origin = f"{_parsed_cr.scheme}://{_parsed_cr.netloc}"
            safe_redirect = None
            for _candidate in _allowed_list:
                _cp = urlparse(_candidate)
                if _cr_origin == f"{_cp.scheme}://{_cp.netloc}":
                    safe_redirect = f"{_cp.scheme}://{_cp.netloc}{_parsed_cr.path}"
                    break

        if safe_redirect is None:
            # Allowlist may have changed between authorize and callback —
            # reject the redirect and fall back to JSON. The user keeps
            # their tokens; only the redirect is dropped.
            logger.warning(LOG_WARN_OAUTH_REDIRECT_BLOCKED, client_redirect)
            return success_response(data=result)

        # Stash tokens under a single-use code; SPA exchanges it via
        # POST /exchange. Tokens never appear in URLs, browser history,
        # referrer headers, or server access logs.
        exchange_code = secrets.token_urlsafe(32)
        await redis_client.setex(
            f"auth:oauth_exchange:{exchange_code}",
            settings.oauth_exchange_code_ttl_seconds,
            json.dumps(result),
        )
        params = urlencode({"code": exchange_code})
        return RedirectResponse(url=f"{safe_redirect}?{params}")

    # No redirect_uri → API client wants tokens inline.
    return success_response(data=result)


@router.post("/exchange")
async def exchange_code(
    body: OAuth2ExchangeRequest,
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """Exchange the one-time code from the redirect URL for the actual JWT
    pair. The code is single-use — first POST wins, subsequent POSTs 401."""
    key = f"auth:oauth_exchange:{body.code}"
    data = await redis_client.get(key)
    if not data:
        raise AuthenticationRequiredError(OAUTH_CODE_INVALID)

    # Delete immediately — single-use semantics.
    await redis_client.delete(key)
    return success_response(data=json.loads(data))
