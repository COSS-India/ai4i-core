"""
OAuth2 routes — thin handlers, all logic in OAuthService.
"""

import json
import logging
import secrets
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import AuthenticationRequiredError, EntityNotFoundError
from app.core.redis import get_redis
from app.core.responses import success_response
from app.dependencies.services import get_oauth_service
from app.schemas.base import BaseSchema
from app.schemas.oauth import OAuth2ProviderInfo
from app.services.oauth_service import OAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oauth2", tags=["OAuth2"])


def _is_redirect_allowed(uri: str) -> bool:
    """
    Validate redirect_uri against the configured allowlist.
    Prevents open redirect / token leakage attacks.
    """
    if not uri:
        return False

    allowed = settings.oauth_allowed_redirect_uris
    if not allowed:
        logger.warning("OAUTH_ALLOWED_REDIRECT_URIS not configured — rejecting redirect to %s", uri)
        return False

    allowed_list = [u.strip() for u in allowed.split(",") if u.strip()]

    # Exact match
    if uri in allowed_list:
        return True

    # Origin match (scheme + host)
    parsed = urlparse(uri)
    uri_origin = f"{parsed.scheme}://{parsed.netloc}"
    for allowed_uri in allowed_list:
        allowed_parsed = urlparse(allowed_uri)
        allowed_origin = f"{allowed_parsed.scheme}://{allowed_parsed.netloc}"
        if uri_origin == allowed_origin:
            return True

    return False


@router.get("/providers")
async def list_providers(svc: OAuthService = Depends(get_oauth_service)):
    providers = []
    for name in ("google", "github"):
        try:
            config = svc.get_provider_config(name)
            if config.get("client_id"):
                providers.append(OAuth2ProviderInfo(
                    provider=name, client_id=config["client_id"],
                    authorization_url=config["authorization_url"], scope=config["scope"],
                ))
        except EntityNotFoundError:
            pass
    return success_response(data=[p.model_dump() for p in providers])


@router.get("/{provider}/authorize")
async def authorize(
    request: Request,
    provider: str,
    redirect_uri: str = Query(None),
    svc: OAuthService = Depends(get_oauth_service),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    config = svc.get_provider_config(provider)
    if not config.get("client_id") or not config.get("client_secret"):
        raise EntityNotFoundError(f"OAuth provider '{provider}' is not configured")

    # Validate redirect_uri BEFORE storing in state
    if redirect_uri and not _is_redirect_allowed(redirect_uri):
        raise AuthenticationRequiredError(
            f"Redirect URI not allowed: {redirect_uri}. "
            "Configure OAUTH_ALLOWED_REDIRECT_URIS."
        )

    state = secrets.token_urlsafe(32)
    await redis_client.setex(
        f"auth:oauth_state:{state}", 600,
        json.dumps({"provider": provider, "redirect_uri": redirect_uri or ""}),
    )

    callback_url = f"{settings.oauth_redirect_base_url or ''}/api/v1/auth/oauth2/{provider}/callback"
    params = {
        "client_id": config["client_id"],
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(config["scope"]),
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    auth_url = f"{config['authorization_url']}?{urlencode(params)}"

    # Browser navigation should go straight to provider consent screen.
    # API clients can still consume JSON as before.
    accept_header = (request.headers.get("accept") or "").lower()
    if "text/html" in accept_header and "application/json" not in accept_header:
        return RedirectResponse(url=auth_url, status_code=307)

    return success_response(data={"authorization_url": auth_url, "state": state})


@router.get("/{provider}/callback")
async def callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    svc: OAuthService = Depends(get_oauth_service),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    state_key = f"auth:oauth_state:{state}"
    state_data_raw = await redis_client.get(state_key)
    if not state_data_raw:
        raise AuthenticationRequiredError("Invalid or expired OAuth state.")
    await redis_client.delete(state_key)

    state_data = json.loads(state_data_raw)
    if state_data.get("provider") != provider:
        raise AuthenticationRequiredError("OAuth provider mismatch.")

    callback_url = f"{settings.oauth_redirect_base_url or ''}/api/v1/auth/oauth2/{provider}/callback"
    result = await svc.complete_oauth_login(provider, code, callback_url)

    # Redirect with a one-time exchange code — NEVER put tokens in URL
    client_redirect = state_data.get("redirect_uri")
    if client_redirect:
        if not _is_redirect_allowed(client_redirect):
            logger.warning("Blocked redirect to unallowed URI: %s", client_redirect)
            return success_response(data=result)

        # Store tokens in Redis under a short-lived exchange code
        exchange_code = secrets.token_urlsafe(32)
        await redis_client.setex(
            f"auth:oauth_exchange:{exchange_code}",
            120,  # 2 minutes TTL
            json.dumps(result),
        )

        # Redirect with code only — client exchanges it via POST /exchange
        params = urlencode({"code": exchange_code})
        return RedirectResponse(url=f"{client_redirect}?{params}")

    # No redirect — return tokens directly (API client, not browser)
    return success_response(data=result)


class _ExchangeCodeRequest(BaseSchema):
    code: str


@router.post("/exchange")
async def exchange_code(
    body: _ExchangeCodeRequest,
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """
    Exchange a one-time OAuth code for tokens.

    The client receives a short-lived code via redirect (not tokens).
    This POST endpoint exchanges that code for actual tokens.
    Tokens never appear in URLs, browser history, referrer headers, or logs.
    """
    key = f"auth:oauth_exchange:{body.code}"
    data = await redis_client.get(key)

    if not data:
        raise AuthenticationRequiredError("Invalid or expired exchange code.")

    # Delete immediately — one-time use
    await redis_client.delete(key)

    return success_response(data=json.loads(data))
