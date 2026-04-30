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
    roles: list[str] = []
    token_type: Optional[str] = None
