"""
RefreshToken request/response schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from app.schemas.base import BaseSchema


class RefreshTokenResponse(BaseSchema):
    user_id: UUID
    refresh_token: str
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
