"""
API versioning for ALL AI4I-Core microservices.

Enterprise pattern: URL versioning (major) + header negotiation (minor).

URL:     /api/v1/auth/login            ← major version in path
Header:  Accept-Version: 2024.03.20    ← optional minor version negotiation

Response headers on every response:
  X-API-Version: v1
  X-Service-Version: 2.0.0
  X-Min-Version: v1                    ← oldest supported major version
  Deprecation: true                    ← if this version is deprecated
  Sunset: 2025-06-01                   ← when this version will be removed

Usage::

    from ai4icore_bootstrap.versioning import APIVersioning

    versioning = APIVersioning(
        service_name="auth-service",
        service_version="2.0.0",
        current_api_version="v1",
        supported_versions=["v1"],
    )

    # Add middleware
    versioning.register(app)

    # Create versioned router
    v1 = versioning.create_router("v1")
    v1.include_router(auth_router)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, FastAPI, Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    """Metadata about a supported API version."""
    version: str                          # "v1"
    deprecated: bool = False              # True if clients should migrate
    sunset_date: Optional[str] = None     # ISO date when this version will be removed


@dataclass
class APIVersioning:
    """
    Enterprise API versioning.

    Manages URL-versioned routers, response version headers,
    and deprecation lifecycle.
    """

    service_name: str
    service_version: str
    current_api_version: str = "v1"
    supported_versions: list[VersionInfo] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.supported_versions:
            self.supported_versions = [VersionInfo(version=self.current_api_version)]
        self._version_map = {v.version: v for v in self.supported_versions}

    def create_router(self, version: str) -> APIRouter:
        """Create a router with /api/{version} prefix."""
        if version not in self._version_map:
            raise ValueError(f"Version '{version}' is not in supported_versions.")
        return APIRouter(prefix=f"/api/{version}")

    def register(self, app: FastAPI) -> None:
        """Register version middleware on the app."""

        min_version = self.supported_versions[0].version if self.supported_versions else self.current_api_version

        @app.middleware("http")
        async def version_headers(request: Request, call_next) -> Response:
            response = await call_next(request)

            # Always set version headers
            response.headers["X-API-Version"] = self.current_api_version
            response.headers["X-Service-Version"] = self.service_version
            response.headers["X-Min-Version"] = min_version

            # Check if requested version is deprecated
            requested_version = self._extract_version(request)
            if requested_version:
                info = self._version_map.get(requested_version)
                if info and info.deprecated:
                    response.headers["Deprecation"] = "true"
                    if info.sunset_date:
                        response.headers["Sunset"] = info.sunset_date

            return response

    def _extract_version(self, request: Request) -> Optional[str]:
        """Extract API version from URL path (/api/v1/...) or Accept-Version header."""
        # URL path
        path = request.url.path
        parts = path.split("/")
        if len(parts) >= 3 and parts[1] == "api":
            return parts[2]

        # Header fallback
        return request.headers.get("Accept-Version")

    def get_version_info(self, version: str) -> Optional[VersionInfo]:
        return self._version_map.get(version)

    @property
    def all_versions(self) -> list[str]:
        return [v.version for v in self.supported_versions]
