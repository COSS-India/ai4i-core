"""
Tenant resolution utilities.
Extracts organization, user_id, and api_key_name from requests.
"""

from typing import Dict, Optional, Callable
from fastapi import Request
from dataclasses import dataclass


@dataclass
class TenantContext:
    """Tenant context extracted from request"""
    organization: str
    user_id: str
    api_key_name: str
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for use in metrics labels"""
        return {
            "organization": self.organization,
            "user_id": self.user_id,
            "api_key_name": self.api_key_name,
        }


def default_tenant_resolver(request: Request) -> TenantContext:
    """
    Default tenant resolver that extracts tenant info from JWT claims or headers.
    
    Priority:
    1. JWT claims (if available in request.state)
    2. HTTP headers (X-Organization-ID, X-User-ID, X-API-Key-Name)
    3. Default values ("unknown", "anonymous", "unknown")
    
    Args:
        request: FastAPI Request object
    
    Returns:
        TenantContext: Extracted tenant information
    
    Example:
        ```python
        tenant = default_tenant_resolver(request)
        # Use tenant.organization, tenant.user_id, tenant.api_key_name
        ```
    """
    # Try to get from JWT claims (set by auth middleware)
    organization = "unknown"
    user_id = "anonymous"
    api_key_name = "unknown"
    
    # Check request.state for JWT claims (common pattern)
    if hasattr(request.state, "organization"):
        organization = request.state.organization
    elif hasattr(request.state, "org_id"):
        organization = request.state.org_id
    
    if hasattr(request.state, "user_id"):
        user_id = request.state.user_id
    
    if hasattr(request.state, "api_key_name"):
        api_key_name = request.state.api_key_name
    elif hasattr(request.state, "api_key_id"):
        api_key_name = str(request.state.api_key_id)
    
    # Fallback to headers
    if organization == "unknown":
        organization = request.headers.get("X-Organization-ID", "unknown")
    
    if user_id == "anonymous":
        user_id = request.headers.get("X-User-ID", "anonymous")
    
    if api_key_name == "unknown":
        api_key_name = request.headers.get("X-API-Key-Name", "unknown")
    
    return TenantContext(
        organization=organization,
        user_id=user_id,
        api_key_name=api_key_name,
    )


def create_custom_tenant_resolver(
    org_extractor: Callable[[Request], str],
    user_extractor: Callable[[Request], str],
    api_key_extractor: Callable[[Request], str],
) -> Callable[[Request], TenantContext]:
    """
    Create a custom tenant resolver from extraction functions.
    
    Args:
        org_extractor: Function to extract organization from Request
        user_extractor: Function to extract user_id from Request
        api_key_extractor: Function to extract api_key_name from Request
    
    Returns:
        Callable that takes Request and returns TenantContext
    
    Example:
        ```python
        def get_org_from_db(request):
            # Custom logic to get org from database
            return "custom_org"
        
        custom_resolver = create_custom_tenant_resolver(
            org_extractor=get_org_from_db,
            user_extractor=lambda r: r.state.user_id,
            api_key_extractor=lambda r: r.state.api_key_name,
        )
        
        init_observability(app, "nmt", tenant_resolver=custom_resolver)
        ```
    """
    def resolver(request: Request) -> TenantContext:
        return TenantContext(
            organization=org_extractor(request),
            user_id=user_extractor(request),
            api_key_name=api_key_extractor(request),
        )
    
    return resolver

