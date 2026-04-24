"""
OAuth2 schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from app.schemas.base import BaseSchema


class OAuth2ProviderInfo(BaseSchema):
    provider: str
    client_id: str
    authorization_url: str
    scope: list[str] = []


class OAuth2CallbackRequest(BaseSchema):
    code: str
    state: str
    provider: str


class OAuthProviderResponse(BaseSchema):
    id: int
    user_id: UUID
    provider_name: str
    provider_user_id: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
