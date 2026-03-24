"""
Shared auth middleware for all microservices.

Every service uses this middleware to:
1. Validate JWT (RS256)
2. Populate request.state with auth context
3. Optionally enforce auth (or just extract context for logging)

Usage::

    from ai4icore_auth import AuthMiddleware
    from ai4icore_auth.providers import build_jwt_verifier

    verifier = build_jwt_verifier()  # reads JWKS_URL, JWT_ISSUER from env
    await verifier.initialize()

    app.add_middleware(AuthMiddleware, jwt_verifier=verifier)
"""

import logging
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from .jwt_verifier import AuthClaims, JWTVerifier, JWTVerificationError, JWTExpiredError

logger = logging.getLogger(__name__)

# Paths that skip auth
_DEFAULT_SKIP_PATHS = {"/", "/health", "/ready", "/docs", "/redoc", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Standard auth middleware for all AI4I microservices.

    Validates JWT, populates request.state, optionally enforces permissions.

    Supports two initialization modes:
    - Direct: pass jwt_verifier instance at construction
    - Lazy: pass jwt_verifier_factory callable (resolved on first request)
    """

    def __init__(
        self,
        app,
        jwt_verifier: Optional[JWTVerifier] = None,
        jwt_verifier_factory: Optional[Callable[[], JWTVerifier]] = None,
        service_name: str = "",
        skip_paths: Optional[set[str]] = None,
        require_auth: bool = True,
        allow_anonymous_paths: Optional[set[str]] = None,
    ) -> None:
        super().__init__(app)
        self._verifier = jwt_verifier
        self._verifier_factory = jwt_verifier_factory
        self._skip_paths = skip_paths or _DEFAULT_SKIP_PATHS
        self._require_auth = require_auth
        self._allow_anonymous = allow_anonymous_paths or set()

    def _get_verifier(self) -> Optional[JWTVerifier]:
        """Resolve verifier: direct instance or lazy factory."""
        if self._verifier is not None:
            return self._verifier
        if self._verifier_factory is not None:
            try:
                self._verifier = self._verifier_factory()
                return self._verifier
            except RuntimeError:
                return None
        return None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip auth for health/docs/etc.
        if request.url.path in self._skip_paths:
            self._set_anonymous(request)
            return await call_next(request)

        # Extract token
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        # No token
        if not token:
            if request.url.path in self._allow_anonymous or not self._require_auth:
                self._set_anonymous(request)
                return await call_next(request)
            return self._auth_error("Authentication required.")

        # Get verifier
        verifier = self._get_verifier()
        if verifier is None:
            if not self._require_auth:
                self._set_anonymous(request)
                return await call_next(request)
            return self._auth_error("Auth verifier not available.")

        # Verify JWT
        try:
            claims = await verifier.verify(token)
        except JWTExpiredError:
            if self._require_auth:
                return self._auth_error("Token has expired.", status_code=401)
            self._set_anonymous(request)
            return await call_next(request)
        except JWTVerificationError as exc:
            if self._require_auth:
                return self._auth_error(exc.message, status_code=401)
            self._set_anonymous(request)
            return await call_next(request)

        # Populate request.state
        self._set_claims(request, claims)

        return await call_next(request)

    @staticmethod
    def _set_claims(request: Request, claims: AuthClaims) -> None:
        request.state.user_id = claims.user_id
        request.state.tenant_id = claims.tenant_id
        request.state.permission_ids = claims.permission_ids
        request.state.permissions = claims.permissions
        request.state.roles = claims.roles
        request.state.token_type = claims.token_type
        request.state.token_id = claims.token_id
        request.state.username = claims.username
        request.state.email = claims.email
        request.state.is_authenticated = True
        request.state.jwt_claims = claims

    @staticmethod
    def _set_anonymous(request: Request) -> None:
        request.state.user_id = None
        request.state.tenant_id = None
        request.state.permission_ids = []
        request.state.permissions = []
        request.state.roles = []
        request.state.token_type = None
        request.state.token_id = None
        request.state.username = None
        request.state.email = None
        request.state.is_authenticated = False
        request.state.jwt_claims = None

    @staticmethod
    def _auth_error(message: str, status_code: int = 401) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": {
                    "code": "AUTHENTICATION_REQUIRED" if status_code == 401 else "FORBIDDEN",
                    "message": message,
                },
            },
        )
