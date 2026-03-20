"""
Token-related schemas.
"""

from typing import Optional

from app.schemas.base import BaseSchema


class TokenValidationResponse(BaseSchema):
    valid: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    tenant_id: Optional[str] = None
    permission_ids: list[int] = []
    permissions: list[str] = []  # Permission names for v1 compatibility
    roles: list[str] = []
    token_type: Optional[str] = None
