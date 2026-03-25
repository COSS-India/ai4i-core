"""
OAuth2 schemas.
"""

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
