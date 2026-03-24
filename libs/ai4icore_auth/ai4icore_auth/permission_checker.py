"""
Shared permission checking — NO service-local permission logic allowed.

This is the single enforcement point for permission checks across all services.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PermissionChecker:
    """
    Checks if a user/API key has the required permission for an endpoint.

    Usage::

        checker = PermissionChecker(redis_client=redis)
        await checker.load_api_permission_map("/path/to/api_permissions.json")

        # Check if user has permission for this endpoint
        allowed = await checker.check(
            method="POST",
            path="/api/v1/asr/inference",
            user_permission_ids=[1, 5, 12],
        )

        # Or check by permission name
        allowed = checker.has_permission("asr.inference", user_permissions=["asr.inference", "tts.read"])
    """

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client
        self._api_permission_map: dict[str, str] = {}

    async def load_api_permission_map(self, json_path: Optional[str] = None) -> None:
        """
        Load endpoint → required permission code mapping from JSON file and cache in Redis.
        Entries with null permissionRequired are public endpoints (skipped).
        """
        if json_path:
            import pathlib
            data = json.loads(pathlib.Path(json_path).read_text())
            mappings = data.get("apiMappings", [])
            self._api_permission_map = {
                m["endpoint"]: m["permissionRequired"]
                for m in mappings
                if "endpoint" in m and m.get("permissionRequired") is not None
            }

            # Cache in Redis if available
            if self._redis:
                await self._redis.setex(
                    "auth:api_perms",
                    3600,
                    json.dumps(self._api_permission_map),
                )
            logger.info("Loaded %d API permission mappings.", len(self._api_permission_map))

    async def get_required_permission(self, method: str, path: str) -> Optional[str]:
        """
        Look up the required permission for an endpoint.
        Supports exact match and path templates (e.g., /api-keys/{key_id}).
        """
        endpoint_key = f"{method.upper()}:{path}"

        # Load mapping from local cache or Redis
        mapping = self._api_permission_map
        if not mapping and self._redis:
            data = await self._redis.get("auth:api_perms")
            if data:
                mapping = json.loads(data)

        if not mapping:
            return None

        # 1. Exact match (fast path — most endpoints)
        if endpoint_key in mapping:
            return mapping[endpoint_key]

        # 2. Template match (for paths like /api-keys/{key_id})
        method_upper = method.upper()
        path_segments = path.rstrip("/").split("/")
        for pattern, perm in mapping.items():
            if not pattern.startswith(f"{method_upper}:"):
                continue
            pattern_path = pattern.split(":", 1)[1]
            pattern_segments = pattern_path.rstrip("/").split("/")
            if len(pattern_segments) != len(path_segments):
                continue
            if all(
                ps == rs or (ps.startswith("{") and ps.endswith("}"))
                for ps, rs in zip(pattern_segments, path_segments)
            ):
                return perm

        return None

    @staticmethod
    def check_endpoint_access(
        required: int | str | None,
        user_permission_ids: list[int] | None = None,
        user_roles: list[str] | None = None,
    ) -> bool:
        """
        Shared endpoint permission check. Single source of truth.

        Checks permission_id (int) from JWT against required endpoint permission.
        ADMIN role bypasses all checks.

        Returns True if access should be granted, False if denied.
        """
        if required is None:
            return True

        # Check by permission ID
        if isinstance(required, int) or (isinstance(required, str) and required.isdigit()):
            req_id = int(required)
            if user_permission_ids and req_id in user_permission_ids:
                return True

        # ADMIN bypass
        if user_roles and "ADMIN" in user_roles:
            return True

        return False

    @staticmethod
    def has_permission(required: str, user_permissions: list[str]) -> bool:
        """Check if the required permission is in the user's permission list."""
        if not required:
            return True
        return required in user_permissions

    @staticmethod
    def has_permission_id(required_id: int, user_permission_ids: list[int]) -> bool:
        """Check if the required permission ID is in the user's list."""
        if not required_id:
            return True
        return required_id in user_permission_ids

    @staticmethod
    def has_any_role(required_roles: list[str], user_roles: list[str]) -> bool:
        """Check if the user has any of the required roles."""
        return bool(set(required_roles) & set(user_roles))

    @staticmethod
    def is_superuser(claims) -> bool:
        """Check if claims indicate a superuser (convention: 'ADMIN' role or superuser flag)."""
        if hasattr(claims, "roles"):
            return "ADMIN" in claims.roles
        return False
