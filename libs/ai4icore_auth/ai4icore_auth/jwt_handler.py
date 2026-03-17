"""JWT token validation and user extraction."""

import logging
from typing import Optional, Dict, Any

from fastapi import Request
from jose import JWTError, jwt

from ai4icore_constants.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


class JWTHandler:
    """Handles local JWT verification and user context extraction."""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm

    async def authenticate_bearer_token(
        self,
        request: Request,
        authorization: Optional[str],
    ) -> Dict[str, Any]:
        """Validate JWT locally and populate request.state.

        Returns dict with user_id, api_key_id, user, api_key, jwt_payload.
        """
        if not authorization:
            raise AuthenticationError("No authorization header provided")

        token = authorization
        if token.startswith("Bearer "):
            token = token[7:]

        if not token:
            raise AuthenticationError("Empty token")

        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
        except JWTError as e:
            logger.warning("JWT verification failed: %s", str(e))
            raise AuthenticationError(f"Invalid token: {e}")

        token_type = payload.get("type", "access")
        if token_type != "access":
            raise AuthenticationError(f"Invalid token type: {token_type}")

        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise AuthenticationError("Token missing user identifier")

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            raise AuthenticationError("Invalid user_id in token")

        email = payload.get("email", "")
        username = payload.get("username", "")
        roles = payload.get("roles", [])

        # Populate request state
        request.state.user_id = user_id
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = email
        request.state.is_authenticated = True
        request.state.jwt_payload = payload

        # Extract tenant context from JWT if present
        if hasattr(payload, "get"):
            schema_name = payload.get("schema_name") or payload.get("tenant_schema")
            if schema_name:
                request.state.tenant_schema = schema_name
            tenant_id = payload.get("tenant_id")
            if tenant_id:
                request.state.tenant_id = tenant_id
            tenant_uuid = payload.get("tenant_uuid")
            if tenant_uuid:
                request.state.tenant_uuid = tenant_uuid

        return {
            "user_id": user_id,
            "api_key_id": None,
            "user": {
                "id": user_id,
                "username": username,
                "email": email,
                "roles": roles,
            },
            "api_key": None,
            "jwt_payload": payload,
        }
