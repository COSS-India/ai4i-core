"""Shared pay-per-use metering for NMT (used by ``routers/inference_router`` and ``app/routes/inference``).

Docker runs ``uvicorn app.main:app``, so the live inference path is ``app/routes/inference.py``.
Both entrypoints must call these helpers or usage/wallet rows never update.
"""

from __future__ import annotations

import inspect
from typing import Any, Optional

from fastapi import HTTPException, Request
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from ai4icore_env import app_env
from ai4icore_logging import get_logger
from ai4icore_multi_tenant import (
    PayPerUseClient,
    ppu_actor_key,
    try_get_tenant_context,
)

logger = get_logger(__name__)

tracer = trace.get_tracer("nmt-service")

API_GATEWAY_URL = app_env.api_gateway_url


def _set_billing_service_fields(span, http_request: Request, service_id: str) -> None:
    """Emit service id; set billing.service_name from MM registry name on request.state only."""
    span.set_attribute("billing.service_id", str(service_id or ""))
    name = (getattr(http_request.state, "billing_service_name", None) or "").strip()
    if name:
        span.set_attribute("billing.service_name", name)


def _pay_per_use_check_is_short_circuit() -> bool:
    """True when PayPerUseClient.check does not perform an active HTTP client.post (see client source)."""
    src_lines = inspect.getsourcelines(PayPerUseClient.check)[0]
    body_lines = []
    for line in src_lines:
        if line.strip().startswith("#"):
            continue
        body_lines.append(line)
    body = "".join(body_lines)
    return "client.post" not in body


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
    with tracer.start_as_current_span("pay_per_use.check") as span:
        ppu = PayPerUseClient()
        tenant_id = await _ppu_tenant_id_nmt(http_request)
        actor = ppu_actor_key(http_request)
        if not ppu.base_url:
            if tenant_id:
                logger.warning(
                    "pay_per_use: base URL not configured; skipping quota/wallet pre-check for tenant_id=%s",
                    tenant_id,
                )
            u_early = int(round(max(float(units), 1.0)))
            span.set_attribute("billing.tenant_id", tenant_id or "")
            _set_billing_service_fields(span, http_request, service_id)
            span.set_attribute("billing.units", u_early)
            span.set_attribute("billing.check_outcome", "skipped")
            span.set_attribute("billing.check_status", "short_circuit")
            logger.info(
                "ppu_check",
                extra={
                    "billing.tenant_id": tenant_id or "",
                    "billing.service_id": service_id or "",
                    "billing.units": u_early,
                    "billing.check_outcome": "skipped",
                    "billing.check_status": "short_circuit",
                    "status": "skipped",
                },
            )
            return
        if not tenant_id or actor is None or not service_id:
            logger.warning(
                "pay_per_use SKIP check: tenant_id=%r actor=%r service_id=%r",
                tenant_id,
                actor,
                service_id,
            )
            u_early = int(round(max(float(units), 1.0)))
            span.set_attribute("billing.tenant_id", tenant_id or "")
            _set_billing_service_fields(span, http_request, service_id)
            span.set_attribute("billing.units", u_early)
            span.set_attribute("billing.check_outcome", "skipped")
            span.set_attribute("billing.check_status", "short_circuit")
            logger.info(
                "ppu_check",
                extra={
                    "billing.tenant_id": tenant_id or "",
                    "billing.service_id": service_id or "",
                    "billing.units": u_early,
                    "billing.check_outcome": "skipped",
                    "billing.check_status": "short_circuit",
                    "status": "skipped",
                },
            )
            return
        u = max(float(units), 1.0)
        span.set_attribute("billing.tenant_id", tenant_id)
        _set_billing_service_fields(span, http_request, service_id)
        span.set_attribute("billing.units", int(round(u)))
        check_status = "short_circuit" if _pay_per_use_check_is_short_circuit() else "real"
        try:
            ok = await ppu.check(tenant_id, actor, str(service_id), u)
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
        if check_status == "short_circuit":
            outcome = "skipped"
        else:
            outcome = "allowed" if ok else "denied"
        span.set_attribute("billing.check_outcome", outcome)
        span.set_attribute("billing.check_status", check_status)
        logger.info(
            "ppu_check",
            extra={
                "billing.tenant_id": tenant_id,
                "billing.service_id": service_id,
                "billing.units": int(round(u)),
                "billing.check_outcome": outcome,
                "billing.check_status": check_status,
                "status": "skipped" if outcome == "skipped" else ("allowed" if ok else "denied"),
            },
        )
        if not ok:
            raise HTTPException(status_code=429, detail="Pay-per-use check failed")


async def _nmt_ppu_record(http_request: Request, service_id: str, units: float) -> None:
    with tracer.start_as_current_span("pay_per_use.record") as span:
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
            u_early = int(round(max(float(units), 1.0)))
            span.set_attribute("billing.tenant_id", tenant_id or "")
            _set_billing_service_fields(span, http_request, service_id)
            span.set_attribute("billing.units", u_early)
            span.set_attribute("billing.recorded", False)
            logger.info(
                "ppu_record",
                extra={
                    "billing.tenant_id": tenant_id or "",
                    "billing.service_id": service_id or "",
                    "billing.units": u_early,
                    "billing.cost": 0.0,
                    "billing.remaining_balance": 0.0,
                    "billing.recorded": False,
                    "status": "skipped",
                },
            )
            return
        if not tenant_id or actor is None or not service_id:
            logger.warning(
                "pay_per_use SKIP record: tenant_id=%r actor=%r service_id=%r",
                tenant_id,
                actor,
                service_id,
            )
            u_early = int(round(max(float(units), 1.0)))
            span.set_attribute("billing.tenant_id", tenant_id or "")
            _set_billing_service_fields(span, http_request, service_id)
            span.set_attribute("billing.units", u_early)
            span.set_attribute("billing.recorded", False)
            logger.info(
                "ppu_record",
                extra={
                    "billing.tenant_id": tenant_id or "",
                    "billing.service_id": service_id or "",
                    "billing.units": u_early,
                    "billing.cost": 0.0,
                    "billing.remaining_balance": 0.0,
                    "billing.recorded": False,
                    "status": "skipped",
                },
            )
            return
        u = max(float(units), 1.0)
        span.set_attribute("billing.tenant_id", tenant_id)
        _set_billing_service_fields(span, http_request, service_id)
        span.set_attribute("billing.units", int(round(u)))
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
            cost = float(result.get("cost") or 0.0)
            remaining_balance = float(result.get("remaining_balance") or 0.0)
            if isinstance(result, dict) and result.get("error") is not None:
                err_msg = str(result.get("error"))
                synth = RuntimeError(f"pay_per_use record error payload: {err_msg}")
                span.record_exception(synth)
                span.set_status(Status(StatusCode.ERROR, err_msg))
                span.set_attribute("billing.cost", cost)
                span.set_attribute("billing.remaining_balance", remaining_balance)
                span.set_attribute("billing.recorded", False)
                logger.info(
                    "ppu_record",
                    extra={
                        "billing.tenant_id": tenant_id,
                        "billing.service_id": service_id,
                        "billing.units": int(round(u)),
                        "billing.cost": cost,
                        "billing.remaining_balance": remaining_balance,
                        "billing.recorded": False,
                        "status": "failed",
                    },
                )
                return
            if result.get("recorded") is False:
                synth = RuntimeError("pay_per_use record returned recorded=false")
                span.record_exception(synth)
                span.set_status(Status(StatusCode.ERROR, "recorded=false"))
                span.set_attribute("billing.cost", cost)
                span.set_attribute("billing.remaining_balance", remaining_balance)
                span.set_attribute("billing.recorded", False)
                logger.info(
                    "ppu_record",
                    extra={
                        "billing.tenant_id": tenant_id,
                        "billing.service_id": service_id,
                        "billing.units": int(round(u)),
                        "billing.cost": cost,
                        "billing.remaining_balance": remaining_balance,
                        "billing.recorded": False,
                        "status": "failed",
                    },
                )
                return
            span.set_attribute("billing.cost", cost)
            span.set_attribute("billing.remaining_balance", remaining_balance)
            span.set_attribute("billing.recorded", True)
            logger.info(
                "ppu_record",
                extra={
                    "billing.tenant_id": tenant_id,
                    "billing.service_id": service_id,
                    "billing.units": int(round(u)),
                    "billing.cost": cost,
                    "billing.remaining_balance": remaining_balance,
                    "billing.recorded": True,
                    "status": "recorded",
                },
            )
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.set_attribute("billing.recorded", False)
            logger.info(
                "ppu_record",
                extra={
                    "billing.tenant_id": tenant_id,
                    "billing.service_id": service_id,
                    "billing.units": int(round(u)),
                    "billing.cost": 0.0,
                    "billing.remaining_balance": 0.0,
                    "billing.recorded": False,
                    "status": "failed",
                },
            )
            logger.warning("pay_per_use record failed: %s", e)
