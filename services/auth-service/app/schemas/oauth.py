"""
OAuth2 schemas.
"""

from app.schemas.base import BaseSchema


class OAuth2ProviderInfo(BaseSchema):
    provider: str
    client_id: str
    authorization_url: str
    scope: list[str] = []


class OAuth2ExchangeRequest(BaseSchema):
    """One-time code exchange — sent by the SPA after the OAuth redirect."""

    code: str
