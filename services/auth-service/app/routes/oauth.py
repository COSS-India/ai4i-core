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
from urllib.parse import urlencode, urlparse, urlunparse

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


def _get_allowed_redirect(uri: str) -> str | None:
    """Return a safe redirect URI if permitted by the configured allowlist, else None.

    Always returns a bare callback URL built only from the matching allowlist
    entry's scheme, host, and path (never query/fragment, never user input).
    Matching is byte-exact on those three components — trailing slash, host
    case, and explicit default ports must match the SPA and the env value.
    Query strings on the request are ignored for matching.
    """
    if not uri:
        return None

    parsed = urlparse(uri)
    if parsed.scheme not in ("https", "http"):
        return None
    # Reject credentials-in-URL and non-empty fragments before allowlist compare.
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        return None

    allowed = settings.oauth_allowed_redirect_uris
    if not allowed:
        logger.warning(LOG_WARN_CONFIG_REDIRECT_ALLOWLIST)
        return None

    allowed_list = [u.strip() for u in allowed.split(",") if u.strip()]
    request_key = (parsed.scheme, parsed.netloc, parsed.path)
    for allowed_uri in allowed_list:
        allowed_parsed = urlparse(allowed_uri)
        if allowed_parsed.scheme not in ("https", "http"):
            continue
        if request_key == (
            allowed_parsed.scheme,
            allowed_parsed.netloc,
            allowed_parsed.path,
        ):
            # Bare URL from server config only — strip query/fragment so the
            # callback can safely append ?code=... without producing entry?x=1?code=.
            return urlunparse(
                (
                    allowed_parsed.scheme,
                    allowed_parsed.netloc,
                    allowed_parsed.path,
                    "",
                    "",
                    "",
                )
            )

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

    # Resolve redirect_uri against the allowlist BEFORE persisting in state.
    # Store the allowlist entry (server config), never the raw client value,
    # so the callback redirect target cannot be influenced by user input.
    safe_client_redirect = ""
    if client_redirect_uri:
        resolved = _get_allowed_redirect(client_redirect_uri)
        if not resolved:
            logger.warning(LOG_WARN_OAUTH_REDIRECT_INVALID, client_redirect_uri)
            raise AuthenticationRequiredError(OAUTH_REDIRECT_URI_INVALID)
        safe_client_redirect = resolved

    state = secrets.token_urlsafe(32)
    await redis_client.setex(
        f"auth:oauth_state:{state}",
        settings.oauth_state_ttl_seconds,
        json.dumps({"provider": config["provider"], "redirect_uri": safe_client_redirect}),
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
        # Re-check against the allowlist at callback time. The returned value
        # is always a verbatim entry from server config — never built from
        # the stored client redirect_uri — so RedirectResponse cannot become
        # an open redirect even if Redis state were tampered with.
        safe_redirect = _get_allowed_redirect(client_redirect)
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
