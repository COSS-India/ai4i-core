from typing import Optional
from uuid import UUID

from fastapi import Depends, Header , status, HTTPException
from fastapi.security import APIKeyHeader, HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .auth_token_provider import fetch_session as auth_token_fetch_session
from .api_key_provider import fetch_session as api_key_fetch_session
from models.token_enum import TokenType
from db_connection import get_auth_db_session


async def InjectRequestSession(
    x_auth_source: TokenType = Header(default=TokenType.API_KEY, alias="x-auth-source"),
    credentials_bearer: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    credentials_key: Optional[str] = Depends(APIKeyHeader(name="X-API-Key", auto_error=False)),
    db: Session = Depends(get_auth_db_session),
):
    """
    Injects session details from request data into a view function.

    WARNING: Only use in protected routes, otherwise it will throw an error.
    """

    if x_auth_source == TokenType.AUTH_TOKEN:
        if not credentials_bearer or credentials_bearer.scheme.lower() != "bearer":
            raise HTTPException(401, "Bearer token required")

        session = await auth_token_fetch_session(
            credentials_bearer.credentials, db
        )

    elif x_auth_source == TokenType.API_KEY:
        if not credentials_key:
            raise HTTPException(401, "API key required")

        session = await api_key_fetch_session(credentials_key, db)

    else:
        raise HTTPException(400, "Route not protected by authentication")
    
    if session is None:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired credentials",
            )

    return RequestSession(**session)


class RequestSession(BaseModel):
    id: str
    name: str
    email: EmailStr
    # role: str

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {UUID: str}


