"""Lightweight JWT payload access for tenant-scoped routes (matches gateway-forwarded Bearer tokens)."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger("pay-per-use-auth")


def decode_jwt_payload_unverified(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None


def _role_strings(payload: Dict[str, Any]) -> List[str]:
    roles = payload.get("roles") or []
    if not isinstance(roles, list):
        return []
    return [str(r) for r in roles]


def is_adopter_admin_payload(payload: Dict[str, Any]) -> bool:
    if payload.get("is_superuser"):
        return True
    for r in _role_strings(payload):
        u = r.upper()
        if u in ("ADMIN", "ADOPTER_ADMIN", "SUPER_ADMIN", "SUPERUSER"):
            return True
    return False


def is_tenant_admin_payload(payload: Dict[str, Any]) -> bool:
    for r in _role_strings(payload):
        u = r.upper()
        if "TENANT" in u and "ADMIN" in u:
            return True
        if u in ("TENANT_ADMIN", "TENANT-ADMIN"):
            return True
    return False


def require_bearer_payload(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization") or request.headers.get("authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_jwt_payload_unverified(auth[7:].strip())
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def assert_tenant_usage_access(request: Request, path_tenant_id: str) -> None:
    payload = require_bearer_payload(request)
    if is_adopter_admin_payload(payload):
        return
    if is_tenant_admin_payload(payload):
        tid = str(payload.get("tenant_id") or "")
        if tid != str(path_tenant_id):
            raise HTTPException(
                status_code=403,
                detail="Access denied — you can only view your own usage",
            )
        return
    raise HTTPException(status_code=403, detail="Access denied")


def assert_adopter_usage_access(request: Request) -> None:
    payload = require_bearer_payload(request)
    if not is_adopter_admin_payload(payload):
        raise HTTPException(status_code=403, detail="Adopter admin access required")


def assert_wallet_access(request: Request, path_tenant_id: str) -> None:
    """Adopter admins may manage any tenant wallet; tenant admins only their own."""
    payload = require_bearer_payload(request)
    if is_adopter_admin_payload(payload):
        return
    if is_tenant_admin_payload(payload):
        tid = str(payload.get("tenant_id") or "")
        if tid != str(path_tenant_id):
            raise HTTPException(
                status_code=403,
                detail="Access denied — you can only view your own usage",
            )
        return
    raise HTTPException(status_code=403, detail="Access denied")
