"""
OAuth2 schemas.
"""

from pydantic import ConfigDict

from app.schemas.auth import LoginResponse
from app.schemas.base import BaseSchema
from app.schemas.common import SuccessResponse


class OAuth2ProviderInfo(BaseSchema):
    provider: str
    client_id: str
    authorization_url: str
    scope: list[str] = []


_OAUTH2_EXCHANGE_REQUEST_EXAMPLE = {
    "code": "<authorization-code-from-oauth-redirect>",
}


class OAuth2ExchangeRequest(BaseSchema):
    """One-time code exchange — sent by the SPA after the OAuth redirect."""

    model_config = ConfigDict(json_schema_extra={"examples": [_OAUTH2_EXCHANGE_REQUEST_EXAMPLE]})

    code: str


class AuthorizeData(BaseSchema):
    authorization_url: str
    state: str


class ListProvidersResponse(SuccessResponse):
    """GET /auth/oauth2/providers"""

    data: list[OAuth2ProviderInfo]


class AuthorizeResponse(SuccessResponse):
    """GET /auth/oauth2/{provider}/authorize — JSON (Accept: application/json)."""

    data: AuthorizeData


class CallbackResponse(SuccessResponse):
    """GET /auth/oauth2/{provider}/callback — JSON when there is no SPA redirect."""

    data: LoginResponse


class ExchangeCodeResponse(SuccessResponse):
    """POST /auth/oauth2/exchange"""

    data: LoginResponse
