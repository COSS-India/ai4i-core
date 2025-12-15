import os
import logging
from typing import Any, Dict

import httpx
from jose import JWTError, jwt

from ai4icore_auth import (
    AuthenticationError,
    AuthorizationError,
    InvalidAPIKeyError,
    ExpiredAPIKeyError,
)

logger = logging.getLogger(__name__)


class NerAuthValidator:
    """Auth validator for NER service using auth-service and local JWT check."""

    def __init__(self):
        self.auth_service_url = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
        self.auth_http_timeout = float(os.getenv("AUTH_HTTP_TIMEOUT", "5.0"))
        self.jwt_secret_key = os.getenv(
            "JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure"
        )
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")

    async def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        service, action = "ner", "inference"
        try:
            validate_url = f"{self.auth_service_url}/api/v1/auth/validate-api-key"
            async with httpx.AsyncClient(timeout=self.auth_http_timeout) as client:
                response = await client.post(
                    validate_url,
                    json={"api_key": api_key, "service": service, "action": action},
                )

            if response.status_code == 200:
                result = response.json()
                if result.get("valid"):
                    return {
                        "user_id": None,
                        "api_key_id": None,
                        "api_key_name": None,
                        "user_email": None,
                        "user": None,
                        "api_key": {"masked": True},
                    }
                raise AuthorizationError(result.get("message", "Permission denied"))

            try:
                error_data = response.json()
                err_msg = error_data.get("detail") or error_data.get("message") or response.text
            except Exception:
                err_msg = response.text
            raise AuthorizationError(err_msg or "Failed to validate API key permissions")
        except httpx.TimeoutException:
            logger.error("Timeout calling auth-service for permission validation")
            raise AuthorizationError("Permission validation service unavailable")
        except httpx.RequestError as exc:
            logger.error(f"Error calling auth-service: {exc}")
            raise AuthorizationError("Failed to validate API key permissions")

    async def validate_bearer(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret_key,
                algorithms=[self.jwt_algorithm],
                options={"verify_signature": True, "verify_exp": True},
            )
            user_id = payload.get("sub") or payload.get("user_id")
            email = payload.get("email", "")
            username = payload.get("username") or payload.get("email", "")
            roles = payload.get("roles", [])
            token_type = payload.get("type", "")

            if token_type != "access":
                raise AuthenticationError("Invalid token type")
            if not user_id:
                raise AuthenticationError("User ID not found in token")

            return {
                "user_id": int(user_id) if isinstance(user_id, (str, int)) else user_id,
                "api_key_id": None,
                "api_key_name": None,
                "user_email": email,
                "user": {"username": username, "email": email, "roles": roles},
                "api_key": None,
            }
        except JWTError as exc:
            logger.warning(f"JWT verification failed: {exc}")
            raise AuthenticationError("Invalid or expired token")
        except Exception as exc:
            logger.error(f"Unexpected error during JWT verification: {exc}")
            raise AuthenticationError("Failed to verify token")

