"""
Tenant context dependency.
"""

from typing import Optional

from fastapi import Depends

from app.dependencies.auth import get_current_token
from app.services.token_service import TokenPayload


async def get_tenant_id(
    payload: TokenPayload = Depends(get_current_token),
) -> Optional[str]:
    """Extract tenant_id from the current token payload."""
    return payload.tenant_id
