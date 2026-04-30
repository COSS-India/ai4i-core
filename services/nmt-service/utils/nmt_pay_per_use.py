"""Shared pay-per-use metering for NMT (used by ``routers/inference_router`` and ``app/routes/inference``).

Docker runs ``uvicorn app.main:app``, so the live inference path is ``app/routes/inference.py``.
Both entrypoints must call these helpers or usage/wallet rows never update.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Request

from ai4icore_env import app_env
from ai4icore_logging import get_logger
from ai4icore_multi_tenant import (
    PayPerUseClient,
    ppu_actor_key,
    try_get_tenant_context,
)

logger = get_logger(__name__)

API_GATEWAY_URL = app_env.api_gateway_url


async def _ppu_tenant_id_nmt(http_request: Request) -> Optional[str]:
    ctx = await try_get_tenant_context(http_request, API_GATEWAY_URL)
    if ctx and ctx.get("tenant_id"):
        return str(ctx["tenant_id"])
    tid = getattr(http_request.state, "tenant_id", None)
    return str(tid) if tid else None


def _effective_service_id_for_ppu(http_request: Request, *candidates: Any) -> str:
    """Prefer model-resolution / SMR service id on request.state; then body or SMR payload."""
    ordered = (getattr(http_request.state, "service_id", None),) + tuple(candidates)
    for candidate in ordered:
        if candidate is None:
            continue
        s = str(candidate).strip()
        if s and s.lower() != "none":
            return s
    return ""


async def _nmt_ppu_check(http_request: Request, service_id: str, units: float) -> None:
    ppu = PayPerUseClient()
    tenant_id = await _ppu_tenant_id_nmt(http_request)
    actor = ppu_actor_key(http_request)
    if not ppu.base_url:
        if tenant_id:
            logger.warning(
                "pay_per_use: base URL not configured; skipping quota/wallet pre-check for tenant_id=%s",
                tenant_id,
            )
        return
    if not tenant_id or actor is None or not service_id:
        logger.warning(
            "pay_per_use SKIP check: tenant_id=%r actor=%r service_id=%r",
            tenant_id,
            actor,
            service_id,
        )
        return
    u = max(float(units), 1.0)
    ok = await ppu.check(tenant_id, actor, str(service_id), u)
    if not ok:
        raise HTTPException(status_code=429, detail="Pay-per-use check failed")


async def _nmt_ppu_record(http_request: Request, service_id: str, units: float) -> None:
    ppu = PayPerUseClient()
    tenant_id = await _ppu_tenant_id_nmt(http_request)
    actor = ppu_actor_key(http_request)
    if not ppu.base_url:
        if tenant_id:
            logger.warning(
                "pay_per_use: base URL not configured; usage not recorded for tenant_id=%s "
                "(set PAY_PER_USE_URL or PAY_PER_USE_SERVICE_URL)",
                tenant_id,
            )
        return
    if not tenant_id or actor is None or not service_id:
        logger.warning(
            "pay_per_use SKIP record: tenant_id=%r actor=%r service_id=%r",
            tenant_id,
            actor,
            service_id,
        )
        return
    u = max(float(units), 1.0)
    try:
        result = await ppu.record(tenant_id, actor, str(service_id), u)
        logger.info(
            "pay_per_use recorded tenant_id=%s service_id=%s units=%s cost=%s remaining_balance=%s",
            tenant_id,
            service_id,
            u,
            result.get("cost"),
            result.get("remaining_balance"),
        )
    except Exception as e:
        logger.warning("pay_per_use record failed: %s", e)
