"""
Tenant Context Dependency
Extracts tenant information from request and provides to endpoints
"""
from fastapi import Request, HTTPException
from typing import Optional, Dict, Any
import logging
import httpx
import os

logger = logging.getLogger(__name__)

# API Gateway URL for resolving tenant context (all requests go through gateway)
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway-service:8080")


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
    request: Request
) -> Optional[Dict[str, Any]]:
    """
    Resolve tenant context from user_id by calling API Gateway.
    All requests are routed through API Gateway for consistency.
    """
    try:
        # Call API Gateway to resolve tenant from user_id
        resolve_url = f"{API_GATEWAY_URL}/api/v1/multi-tenant/resolve/tenant/from/user/{user_id}"
        
        # Get auth headers from request to forward
        auth_header = request.headers.get("Authorization")
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        
        # Also forward API key if present (for service-to-service calls)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            headers["X-API-Key"] = api_key
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(resolve_url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                # Normal case for non-tenant users - log at debug level to avoid noise
                logger.debug(f"Tenant not found for user_id {user_id}")
                return None
            else:
                logger.error(f"Failed to resolve tenant for user_id {user_id}: {response.status_code} - {response.text}")
                return None
                
    except httpx.TimeoutException:
        logger.error("Timeout calling API Gateway for tenant resolution")
        return None
    except Exception as e:
        logger.error(f"Error resolving tenant from user_id {user_id}: {e}", exc_info=True)
        return None


async def try_get_tenant_context(request: Request) -> Optional[Dict[str, Any]]:
    """
    Best-effort tenant context resolver.
    - Returns tenant context dict when user is a tenant admin or tenant user.
    - Returns None for normal users that are not associated with any tenant.
    This is used by services (like NMT) that should fall back to shared auth_db
    when no tenant association exists, instead of treating it as an error.
    """
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
        # No authenticated user → no tenant context
        return None

    tenant_context = await resolve_tenant_from_user_id(user_id, request)
    if not tenant_context:
        # User exists but is not mapped to any ACTIVE tenant (normal user).
        return None

    request.state.tenant_context = tenant_context
    request.state.tenant_schema = tenant_context.get("schema_name")
    request.state.tenant_id = tenant_context.get("tenant_id")
    return tenant_context


async def get_tenant_context(request: Request) -> Dict[str, Any]:
    """
    Strict tenant context resolver.
    - Used by endpoints that *require* the user to be associated with a tenant.
    - Raises HTTP errors when no tenant context can be resolved.
    """
    tenant_context = await try_get_tenant_context(request)

    if not tenant_context:
        # Differentiate between unauthenticated and non-tenant users
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
