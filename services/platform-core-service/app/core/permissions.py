"""Shared role IDs and permission-parsing helper used across all route modules.

A single source of truth means a role-ID change only needs to be made here.
"""
import re

from fastapi import Request

ROLE_ADMIN = 1
ROLE_MODERATOR = 2
ROLE_TENANT_ADMIN = 5


def permission_ids(request: Request) -> set[int]:
    """Parse X-Permission-IDS header into a set of integer role IDs."""
    raw = request.headers.get("X-Permission-IDS", "")
    return {int(m) for m in re.findall(r"\d+", raw)}
