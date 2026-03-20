"""
Tenant Context - Extracts tenant information from request and provides to endpoints
"""
from fastapi import Request, HTTPException
from typing import Optional, Dict, Any
import logging

import httpx

from ai4icore_env import app_env

logger = logging.getLogger(__name__)

DEFAULT_API_GATEWAY_URL = app_env.api_gateway_url


async def resolve_tenant_from_jwt(jwt_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract tenant context from JWT payload.
    """
    tenant_id = jwt_payload.get("tenant_id")
    if not tenant_id:
        return None

    return {
        "tenant_id": tenant_id,
        "tenant_uuid": jwt_payload.get("tenant_uuid"),
        "schema_name": jwt_payload.get("schema_name"),
        "subscriptions": jwt_payload.get("subscriptions", []),
        "user_subscriptions": jwt_payload.get("user_subscriptions", []),
    }


async def resolve_tenant_from_user_id(
    user_id: int,
    request: Request,
    api_gateway_url: str,
) -> Optional[Dict[str, Any]]:
    """
    Resolve tenant context from user_id by calling API Gateway.
    All requests are routed through API Gateway for consistency.
    """
    try:
        resolve_url = f"{api_gateway_url}/api/v1/multi-tenant/resolve/tenant/from/user?user_id={user_id}"

        auth_header = request.headers.get("Authorization")
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header

        api_key = request.headers.get("X-API-Key")
        if api_key:
            headers["X-API-Key"] = api_key

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(resolve_url, headers=headers)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.debug(f"Tenant not found for user_id {user_id}")
                return None
            else:
                logger.error(
                    f"Failed to resolve tenant for user_id {user_id}: "
                    f"{response.status_code} - {response.text}"
                )
                return None

    except httpx.TimeoutException:
        logger.error("Timeout calling API Gateway for tenant resolution")
        return None
    except Exception as e:
        logger.error(f"Error resolving tenant from user_id {user_id}: {e}", exc_info=True)
        return None


async def try_get_tenant_context(
    request: Request, api_gateway_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Best-effort tenant context resolver.
    - Returns tenant context dict when user is a tenant admin or tenant user.
    - Returns None for normal users that are not associated with any tenant.
    """
    _api_gateway_url = api_gateway_url or DEFAULT_API_GATEWAY_URL
    # Try to get from JWT token (if tenant info is in token)
    jwt_payload = getattr(request.state, "jwt_payload", None)
    if jwt_payload:
        tenant_context = await resolve_tenant_from_jwt(jwt_payload)
        if tenant_context:
            request.state.tenant_context = tenant_context
            request.state.tenant_schema = tenant_context.get("schema_name")
            request.state.tenant_id = tenant_context.get("tenant_id")
            return tenant_context

    # Fallback: resolve from user_id via API Gateway → multi-tenant-service
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return None

    tenant_context = await resolve_tenant_from_user_id(user_id, request, _api_gateway_url)
    if not tenant_context:
        return None

    request.state.tenant_context = tenant_context
    request.state.tenant_schema = tenant_context.get("schema_name")
    request.state.tenant_id = tenant_context.get("tenant_id")
    return tenant_context


async def get_tenant_context(
    request: Request, api_gateway_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Strict tenant context resolver.
    - Used by endpoints that *require* the user to be associated with a tenant.
    - Raises HTTP errors when no tenant context can be resolved.
    """
    _api_gateway_url = api_gateway_url or DEFAULT_API_GATEWAY_URL
    tenant_context = await try_get_tenant_context(request, _api_gateway_url)

    if not tenant_context:
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Authentication required and tenant context not found",
            )
        raise HTTPException(
            status_code=403,
            detail="User is not associated with any active tenant",
        )

    return tenant_context
