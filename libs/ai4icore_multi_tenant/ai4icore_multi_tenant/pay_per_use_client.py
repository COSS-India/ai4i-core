from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

from ai4icore_env import app_env

logger = logging.getLogger(__name__)


def _decode_jwt_payload_unverified(token: str) -> Optional[Dict[str, Any]]:
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


def resolve_pay_per_use_base_url(explicit: Optional[str] = None) -> str:
    """Resolve pay-per-use HTTP base URL (no trailing slash). Reads os.environ at call time."""
    raw = (
        (explicit or "").strip()
        or (os.environ.get("PAY_PER_USE_URL") or "").strip()
        or (os.environ.get("PAY_PER_USE_SERVICE_URL") or "").strip()
        or (app_env.pay_per_use_service_url or "").strip()
    )
    return raw.rstrip("/")


def ppu_actor_key(http_request: Any) -> Optional[str]:
    """
    Identifier for pay-per-use check/record: API key when the request used one,
    otherwise a stable key derived from the JWT user (browser / Bearer-only).
    """
    api_key_id = getattr(http_request.state, "api_key_id", None)
    if api_key_id is not None and str(api_key_id).strip():
        return str(api_key_id)
    user_id = getattr(http_request.state, "user_id", None)
    if user_id is not None:
        return f"jwt-user-{user_id}"
    claims = getattr(http_request.state, "jwt_claims", None)
    if claims is not None:
        uid = getattr(claims, "user_id", None)
        if uid is not None:
            return f"jwt-user-{uid}"
    # Bearer JWT without populated state (some gateway paths) — derive billing key from sub.
    try:
        hdr = http_request.headers.get("Authorization") or http_request.headers.get("authorization") or ""
        if hdr.startswith("Bearer "):
            token = hdr[7:].strip()
            if token.count(".") == 2:
                payload = _decode_jwt_payload_unverified(token)
                if payload:
                    sub = payload.get("sub") or payload.get("user_id")
                    if sub is not None and str(sub).strip():
                        return f"jwt-user-{sub}"
    except Exception:
        pass
    return None


class PayPerUseClient:
    """HTTP client for pay-per-use-service check/record endpoints."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        if base_url and str(base_url).strip():
            self.base_url = str(base_url).rstrip("/")
        else:
            self.base_url = resolve_pay_per_use_base_url()

    # async def check(
    #     self,
    #     tenant_id: str,
    #     api_key_id: str,
    #     service_id: str,
    #     estimated_units: float,
    # ) -> bool:
    #     if not self.base_url:
    #         return True
    #     url = f"{self.base_url}/check"
    #     payload = {
    #         "tenant_id": tenant_id,
    #         "api_key_id": api_key_id,
    #         "service_id": service_id,
    #         "estimated_units": estimated_units,
    #     }
    #     async with httpx.AsyncClient(timeout=15.0) as client:
    #         r = await client.post(url, json=payload)
    #     if r.status_code == 200:
    #         data = r.json()
    #         return bool(data.get("allowed", False))
    #     return False

    async def record(
        self,
        tenant_id: str,
        api_key_id: str,
        service_id: str,
        units_consumed: float,
    ) -> Dict[str, Any]:
        if not self.base_url:
            return {"recorded": False, "cost": 0.0, "remaining_balance": 0.0}
        url = f"{self.base_url}/record"
        payload = {
            "tenant_id": tenant_id,
            "api_key_id": api_key_id,
            "service_id": service_id,
            "units_consumed": units_consumed,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload)
        if r.status_code >= 400:
            body = (r.text or "")[:500]
            logger.warning(
                "pay_per_use record failed status=%s tenant_id=%s service_id=%s body=%s",
                r.status_code,
                tenant_id,
                service_id,
                body,
            )
        r.raise_for_status()
        return r.json()
