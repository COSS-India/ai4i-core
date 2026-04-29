"""
Token verification schemas (for token_verification table).
"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSchema


class TokenVerificationCreate(BaseSchema):
    token: str
    expires_at: datetime


class TokenVerificationResponse(BaseSchema):
    id: int
    token: str
    is_active: bool
    expires_at: datetime
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
