"""
Shared permission checking — NO service-local permission logic allowed.

This is the single enforcement point for permission checks across all services.
"""

from typing import Optional

# Process-wide fallback map (endpoint key → permission id int). Auth-service and
# inference apps populate this once at startup after resolving names → DB IDs.
_GLOBAL_ENDPOINT_PERMISSION_MAP: dict[str, int] = {}


def set_global_endpoint_permission_map(mapping: dict[str, int]) -> None:
    """Replace the process-wide endpoint → permission_id map."""
    _GLOBAL_ENDPOINT_PERMISSION_MAP.clear()
    _GLOBAL_ENDPOINT_PERMISSION_MAP.update(mapping)


def get_global_endpoint_permission_map() -> dict[str, int]:
    """Return a copy of the process-wide endpoint → permission_id map."""
    return dict(_GLOBAL_ENDPOINT_PERMISSION_MAP)


class PermissionChecker:
    """Checks if a user/API key has the required permission for an endpoint."""

    def __init__(self) -> None:
        self._api_permission_map: dict[str, int] = {}
        # Bucket index for path-template fallback: method -> seg_count -> [(seg_specs, perm)]
        # where seg_specs is a pre-built list of (segment, is_placeholder) tuples.
        # Lazily built and invalidated by (id, len) fingerprint of the source mapping.
        self._template_index: dict[str, dict[int, list]] = {}
        self._template_index_fp: tuple[int, int] = (0, 0)

    def _get_template_index(self, mapping: dict[str, str]) -> dict[str, dict[int, list]]:
        fp = (id(mapping), len(mapping))
        if fp == self._template_index_fp and self._template_index:
            return self._template_index

        index: dict[str, dict[int, list]] = {}
        for pattern, perm in mapping.items():
            method, sep, path = pattern.partition(":")
            if not sep:
                continue
            segs = path.rstrip("/").split("/")
            seg_specs = [
                (s, s.startswith("{") and s.endswith("}"))
                for s in segs
            ]
            index.setdefault(method.upper(), {}) \
                 .setdefault(len(segs), []) \
                 .append((seg_specs, perm))

        self._template_index = index
        self._template_index_fp = fp
        return index

    async def get_required_permission(self, method: str, path: str) -> Optional[int]:
        """
        Look up the required permission for an endpoint.
        Supports exact match and path templates (e.g., /api-keys/{key_id}).
        """
        endpoint_key = f"{method.upper()}:{path}"

        mapping = self._api_permission_map or _GLOBAL_ENDPOINT_PERMISSION_MAP

        if not mapping:
            return None

        # 1. Exact match (fast path — most endpoints)
        if endpoint_key in mapping:
            return mapping[endpoint_key]

        # 2. Template match (for paths like /api-keys/{key_id})
        # Bucketed by (method, seg_count) to avoid scanning the whole map.
        method_upper = method.upper()
        path_segments = path.rstrip("/").split("/")
        candidates = self._get_template_index(mapping) \
            .get(method_upper, {}) \
            .get(len(path_segments), [])
        for seg_specs, perm in candidates:
            if all(
                is_placeholder or ps == rs
                for (ps, is_placeholder), rs in zip(seg_specs, path_segments)
            ):
                return perm

        return None

    @staticmethod
    def check_endpoint_access(
        required: int | str | None,
        user_permission_ids: list[int] | None = None,
    ) -> bool:
        """
        Shared endpoint permission check. Single source of truth.

        Compares the required permission_id (int) against the caller's
        permission_ids from their JWT claims. Endpoints without a required
        permission are public. ADMIN role gets all permissions in data
        (seeded), so no role-based bypass is needed here.
        """
        if required is None:
            return True

        if isinstance(required, int) or (isinstance(required, str) and required.isdigit()):
            req_id = int(required)
            if user_permission_ids and req_id in user_permission_ids:
                return True

        return False

    @staticmethod
    def has_permission(required: str, user_permissions: list[str]) -> bool:
        """Check if the required permission is in the user's permission list."""
        if not required:
            return True
        return required in user_permissions

    @staticmethod
    def has_any_role(required_roles: list[str], user_roles: list[str]) -> bool:
        """Check if the user has any of the required roles."""
        return bool(set(required_roles) & set(user_roles))
