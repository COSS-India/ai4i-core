"""
Common tenant and service enforcement logic shared across AI4ICore microservices.
"""
from typing import Optional, Dict, Any

from fastapi import Request, HTTPException
import logging
import httpx

from .tenant_context import DEFAULT_API_GATEWAY_URL, try_get_tenant_context


logger = logging.getLogger(__name__)


async def enforce_tenant_and_service_checks(
    http_request: Request,
    service_name: str,
    api_gateway_url: Optional[str] = None,
    service_unavailable_code: str = "SERVICE_UNAVAILABLE",
    service_inactive_message: str = "Service is not active at the moment. Please contact your administrator",
    cannot_detect_message: str = "Cannot detect service availability. Please contact your administrator",
    timeout_message: str = "Service is temporarily unavailable. Please try again in a few minutes.",
    generic_unavailable_message: str = "Service is temporarily unavailable. Please try again in a few minutes.",
) -> None:
    """
    Common multi-tenant checks used by AI4ICore microservices.

    Execution order:
      1) If tenant context exists, ensure tenant subscribes to this service.
      2) Ensure the service is globally active via /list/services.
      3) If tenant context exists, ensure tenant.status == ACTIVE.
    """
    _api_gateway_url = api_gateway_url or DEFAULT_API_GATEWAY_URL

    # Skip tenant and service availability checks for anonymous Try-It requests.
    # API Gateway forwards X-Try-It: true for /api/v1/try-it calls which proxy to services.
    try_it_header = http_request.headers.get("X-Try-It") or http_request.headers.get("x-try-it")
    if try_it_header and str(try_it_header).strip().lower() == "true":
        return

    headers: Dict[str, str] = {}
    auth_header = http_request.headers.get("Authorization") or http_request.headers.get("authorization")
    if auth_header:
        headers["Authorization"] = auth_header

    x_api_key = http_request.headers.get("X-API-Key") or http_request.headers.get("x-api-key")
    if x_api_key:
        headers["X-API-Key"] = x_api_key

    x_auth_source = http_request.headers.get("X-Auth-Source") or http_request.headers.get("x-auth-source")
    if x_auth_source:
        # Normalize header casing when forwarding
        headers["X-Auth-Source"] = x_auth_source

    # Determine tenant context in a best-effort way.
    tenant_context = getattr(http_request.state, "tenant_context", None)

    tenant_data: Optional[Dict[str, Any]] = tenant_context if tenant_context else None
    tenant_id = (
        tenant_context.get("tenant_id") if tenant_context
        else getattr(http_request.state, "tenant_id", None)
    )

    # If still no tenant info, attempt best-effort resolution (returns None for normal users)
    if not tenant_id:
        try:
            resolved = await try_get_tenant_context(http_request, _api_gateway_url)
            if resolved:
                tenant_context = resolved
                tenant_id = tenant_context.get("tenant_id")
                tenant_data = tenant_context
            else:
                tenant_id = None
        except Exception as e:  # noqa: BLE001
            logger.debug(f"try_get_tenant_context discovery failed: {e}")

    # If we have a tenant, verify subscription and basic tenant info
    if tenant_id:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{_api_gateway_url}/api/v1/multi-tenant/internal/view/tenant",
                    params={"tenant_id": tenant_id},
                    headers=headers,
                )
                if resp.status_code == 200:
                    tenant_data = resp.json()
                    subscriptions = [str(s).lower() for s in (tenant_data.get("subscriptions") or [])]
                    if service_name.lower() not in subscriptions:
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "code": "SERVICE_NOT_SUBSCRIBED",
                                "message": f"Tenant '{tenant_id}' is not subscribed to '{service_name}'",
                            },
                        )
                elif resp.status_code == 404:
                    raise HTTPException(
                        status_code=403,
                        detail={"code": "TENANT_NOT_FOUND", "message": "Tenant not found"},
                    )
                else:
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "TENANT_CHECK_FAILED",
                            "message": "Failed to verify tenant information",
                        },
                    )
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to retrieve tenant info for tenant_id={tenant_id}: {e}")
            raise HTTPException(
                status_code=503,
                detail={"code": "TENANT_CHECK_FAILED", "message": "Failed to verify tenant information"},
            )

    # Next, ensure the service is globally active
    # Multi-tenant endpoints only require Bearer token (not API key)
    # Create headers with only Authorization for multi-tenant service check
    service_check_headers: Dict[str, str] = {}
    if headers.get("Authorization") or headers.get("authorization"):
        service_check_headers["Authorization"] = headers.get("Authorization") or headers.get("authorization")  # type: ignore[assignment]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            svc_resp = await client.get(
                f"{_api_gateway_url}/api/v1/multi-tenant/internal/list/services",
                headers=headers,
            )
            if svc_resp.status_code == 200:
                services = svc_resp.json().get("services", [])
                svc_entry = next(
                    (s for s in services if str(s.get("service_name")).lower() == service_name.lower()),
                    None,
                )
                if not svc_entry or not svc_entry.get("is_active", False):
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": service_unavailable_code,
                            "message": service_inactive_message,
                        },
                    )
            else:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": service_unavailable_code,
                        "message": cannot_detect_message,
                    },
                )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail={
                "code": service_unavailable_code,
                "message": timeout_message,
            },
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to verify service active state for '{service_name}': {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "code": service_unavailable_code,
                "message": generic_unavailable_message,
            },
        )

    # Finally, if tenant context present, enforce tenant status (must be ACTIVE)
    #removing tenant status check since tenant wont be able to login if not active