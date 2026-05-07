"""Pay-per-use metering for LLM authenticated inference and OpenAI-compatible proxy routes.

Uses the same ``PayPerUseClient`` check/record flow for ``POST /api/v1/llm/inference`` and
``POST /api/v1/chat/completions`` / ``POST /api/v1/completions`` when ``LLM_PPU_ENABLED=true``.

Configurable values come from ``ai4icore_env.app_env`` (same as the rest of llm-service).
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, Request
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from ai4icore_env import app_env
from ai4icore_logging import get_logger
from ai4icore_multi_tenant import PayPerUseClient, ppu_actor_key

logger = get_logger(__name__)
tracer = trace.get_tracer("llm-service")


# TOKEN COUNT EXTRACTION PATHS
# The following paths are tried in order when extracting total token count from
# a single inference response dict. Add new paths here as backends evolve —
# never remove old ones.
#   1. response["usage"]["total_tokens"]
#   2. response["usage"]["prompt_tokens"] + ["completion_tokens"]
#   3. response["result"]["usage"]["total_tokens"]
#   4. response["result"]["usage"]["prompt_tokens"] + ["completion_tokens"]
#   5. response["data"]["usage"]["total_tokens"]
#   6. response["meta"]["tokens"]["total"]
#   7. response["tokens_used"]
#   8. response["token_count"]
#   BATCH: response["batch"] = list of per-call dicts — sum successful extractions
#   FALLBACK: character estimate = max(sum(len(t) for t in texts) // 4, 1)


def _llm_ppu_enabled() -> bool:
    return app_env.llm_ppu_enabled is True


def _llm_ppu_service_url() -> str:
    raw = (app_env.pay_per_use_service_url or "").strip()
    if not raw:
        logger.warning("PAY_PER_USE_SERVICE_URL is not set")
    return raw


def _llm_ppu_billing_tier() -> str:
    raw = app_env.llm_ppu_billing_tier
    if raw is None or str(raw).strip() == "":
        return "standard"
    return str(raw).strip()


def _llm_ppu_cost_per_token() -> float:
    """Cost rate per token from env; missing or non-positive values fall back to 0.02."""
    raw = app_env.llm_ppu_cost_per_token
    if raw is None:
        logger.warning("LLM_PPU_COST_PER_TOKEN is not set, using default 0.02")
        return 0.02
    v = float(raw)
    if v <= 0:
        logger.warning(
            "LLM_PPU_COST_PER_TOKEN is non-positive (%s), using default 0.02",
            v,
        )
        return 0.02
    return v


def _effective_service_id_for_ppu() -> str:
    """Service id sent to pay-per-use /check and /record.

    Must match ``service_id`` in the tenant plan's ``allowed_services`` (e.g. ``llm``),
    not an OpenAI model name. Model slugs (containing ``/``) are rejected and mapped to ``llm``.
    """
    raw = (app_env.llm_ppu_service_id or "").strip()
    if not raw or "/" in raw:
        if raw and "/" in raw:
            logger.warning(
                "LLM_PPU_SERVICE_ID=%r looks like a model id, not a plan service_id; using 'llm' for PPU",
                raw,
            )
        return "llm"
    return raw


def _ppu_tenant_id_llm(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if tid is None or str(tid).strip() == "":
        raise RuntimeError(
            "tenant_id missing on request.state; PPU requires authenticated tenant context",
        )
    return str(tid)


def _safe_positive_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        i = int(value)
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def _extract_token_count_single_dict(response: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """Return (token_count, token_source) for one dict; count None if no path matched."""
    if not isinstance(response, dict):
        return None, "character_estimate"

    usage = response.get("usage")
    if isinstance(usage, dict):
        t = _safe_positive_int(usage.get("total_tokens"))
        if t is not None:
            return t, "response_usage"
        p = _safe_positive_int(usage.get("prompt_tokens"))
        c = _safe_positive_int(usage.get("completion_tokens"))
        if p is not None and c is not None:
            return p + c, "response_usage"

    result = response.get("result")
    if isinstance(result, dict):
        u2 = result.get("usage")
        if isinstance(u2, dict):
            t = _safe_positive_int(u2.get("total_tokens"))
            if t is not None:
                return t, "response_usage"
            p = _safe_positive_int(u2.get("prompt_tokens"))
            c = _safe_positive_int(u2.get("completion_tokens"))
            if p is not None and c is not None:
                return p + c, "response_usage"

    data = response.get("data")
    if isinstance(data, dict):
        u3 = data.get("usage")
        if isinstance(u3, dict):
            t = _safe_positive_int(u3.get("total_tokens"))
            if t is not None:
                return t, "response_usage"

    meta = response.get("meta")
    if isinstance(meta, dict):
        tok = meta.get("tokens")
        if isinstance(tok, dict):
            t = _safe_positive_int(tok.get("total"))
            if t is not None:
                return t, "response_usage"

    t = _safe_positive_int(response.get("tokens_used"))
    if t is not None:
        return t, "response_usage"

    t = _safe_positive_int(response.get("token_count"))
    if t is not None:
        return t, "response_usage"

    return None, "character_estimate"


def _extract_token_count(response: Dict[str, Any], fallback_texts: List[str]) -> Tuple[int, str]:
    """Aggregate token count from one dict or a batch wrapper; never returns < 1."""
    batch = response.get("batch") if isinstance(response, dict) else None
    if isinstance(batch, list) and len(batch) > 0:
        total = 0
        any_usage = False
        for item in batch:
            if not isinstance(item, dict):
                continue
            cnt, src = _extract_token_count_single_dict(item)
            if cnt is not None:
                total += cnt
                if src == "response_usage":
                    any_usage = True
        if total > 0:
            return max(total, 1), "response_usage" if any_usage else "character_estimate"

    cnt, src = _extract_token_count_single_dict(response if isinstance(response, dict) else {})
    if cnt is not None:
        return max(cnt, 1), src

    est = max(sum(len(t) for t in fallback_texts) // 4, 1)
    keys = list(response.keys()) if isinstance(response, dict) else []
    logger.warning(
        "PPU token extraction failed for all known paths, using character estimate. "
        "Response keys: %s",
        keys,
    )
    return max(est, 1), "character_estimate"


def _pay_per_use_check_is_short_circuit() -> bool:
    """True when PayPerUseClient.check does not perform an active HTTP client.post."""
    src_lines = inspect.getsourcelines(PayPerUseClient.check)[0]
    body_lines = [ln for ln in src_lines if not ln.strip().startswith("#")]
    body = "".join(body_lines)
    return "client.post" not in body


async def _llm_ppu_check(request: Request, input_texts: List[str]) -> bool:
    if not _llm_ppu_enabled():
        logger.debug("PPU disabled, skipping check")
        return True

    estimated_units = float(max(sum(len(t) for t in input_texts) // 4, 1))
    service_id = _effective_service_id_for_ppu()

    try:
        with tracer.start_as_current_span("pay_per_use.check") as span:
            ppu = PayPerUseClient()
            base = _llm_ppu_service_url()
            if not base:
                span.set_attribute("billing.tenant_id", "")
                span.set_attribute("billing.service_id", service_id)
                span.set_attribute("billing.estimated_units", int(round(estimated_units)))
                span.set_attribute("billing.check_outcome", "skipped")
                logger.info(
                    "billing.check",
                    extra={
                        "billing.tenant_id": "",
                        "billing.service_id": service_id,
                        "billing.estimated_units": int(round(estimated_units)),
                        "billing.check_outcome": "skipped",
                        "outcome": "skipped",
                    },
                )
                return True

            try:
                tenant_id = _ppu_tenant_id_llm(request)
            except RuntimeError as exc:
                logger.warning("pay_per_use SKIP check: %s", exc)
                span.set_attribute("billing.tenant_id", "")
                span.set_attribute("billing.service_id", service_id)
                span.set_attribute("billing.estimated_units", int(round(estimated_units)))
                span.set_attribute("billing.check_outcome", "skipped")
                logger.info(
                    "billing.check",
                    extra={
                        "billing.tenant_id": "",
                        "billing.service_id": service_id,
                        "billing.estimated_units": int(round(estimated_units)),
                        "billing.check_outcome": "skipped",
                        "outcome": "skipped",
                    },
                )
                return True

            actor = ppu_actor_key(request)
            if actor is None:
                logger.warning(
                    "pay_per_use SKIP check: missing actor (api_key_id / user context)",
                )
                span.set_attribute("billing.tenant_id", tenant_id)
                span.set_attribute("billing.service_id", service_id)
                span.set_attribute("billing.estimated_units", int(round(estimated_units)))
                span.set_attribute("billing.check_outcome", "skipped")
                logger.info(
                    "billing.check",
                    extra={
                        "billing.tenant_id": tenant_id,
                        "billing.service_id": service_id,
                        "billing.estimated_units": int(round(estimated_units)),
                        "billing.check_outcome": "skipped",
                        "outcome": "skipped",
                    },
                )
                return True

            span.set_attribute("billing.tenant_id", tenant_id)
            span.set_attribute("billing.service_id", service_id)
            span.set_attribute("billing.estimated_units", int(round(estimated_units)))

            check_status = "short_circuit" if _pay_per_use_check_is_short_circuit() else "real"
            try:
                ok = await ppu.check(tenant_id, actor, str(service_id), estimated_units)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attribute("billing.check_outcome", "skipped")
                logger.exception("billing.check failed open: %s", exc)
                return True

            if check_status == "short_circuit":
                outcome = "skipped"
            else:
                outcome = "allowed" if ok else "denied"
            span.set_attribute("billing.check_outcome", outcome)
            logger.info(
                "billing.check",
                extra={
                    "billing.tenant_id": tenant_id,
                    "billing.service_id": service_id,
                    "billing.estimated_units": int(round(estimated_units)),
                    "billing.check_outcome": outcome,
                    "outcome": outcome,
                },
            )
            return ok
    except Exception:
        logger.exception("billing.check unexpected failure — failing open")
        return True


async def _llm_ppu_record(
    request: Request,
    inference_response: Dict[str, Any],
    input_texts: List[str],
) -> None:
    if not _llm_ppu_enabled():
        logger.debug("PPU disabled, skipping record")
        return

    service_id = _effective_service_id_for_ppu()
    cost_rate = _llm_ppu_cost_per_token()
    tier = _llm_ppu_billing_tier()

    try:
        with tracer.start_as_current_span("pay_per_use.record") as span:
            ppu = PayPerUseClient()
            base = _llm_ppu_service_url()
            units_consumed, token_source = _extract_token_count(
                inference_response if isinstance(inference_response, dict) else {},
                input_texts,
            )
            span.set_attribute("billing.token_source", token_source)
            span.set_attribute("billing.cost_rate", cost_rate)
            span.set_attribute("billing.cost_rate_source", "env_fallback")

            if not base:
                span.set_attribute("billing.tenant_id", "")
                span.set_attribute("billing.service_id", service_id)
                span.set_attribute("billing.units_consumed", int(units_consumed))
                span.set_attribute("billing.record_outcome", "skipped")
                span.set_attribute("billing.cost", 0.0)
                span.set_attribute("billing.remaining_balance", 0.0)
                logger.info(
                    "billing.record",
                    extra={
                        "billing.tenant_id": "",
                        "billing.service_id": service_id,
                        "billing.units": int(units_consumed),
                        "billing.cost": 0.0,
                        "billing.remaining_balance": 0.0,
                        "billing.record_outcome": "skipped",
                        "billing.token_source": token_source,
                        "billing.cost_rate": cost_rate,
                    },
                )
                return

            try:
                tenant_id = _ppu_tenant_id_llm(request)
            except RuntimeError as exc:
                logger.warning("pay_per_use SKIP record: %s", exc)
                span.set_attribute("billing.tenant_id", "")
                span.set_attribute("billing.service_id", service_id)
                span.set_attribute("billing.units_consumed", int(units_consumed))
                span.set_attribute("billing.record_outcome", "skipped")
                span.set_attribute("billing.cost", 0.0)
                span.set_attribute("billing.remaining_balance", 0.0)
                return

            actor = ppu_actor_key(request)
            if actor is None:
                logger.warning("pay_per_use SKIP record: missing actor")
                span.set_attribute("billing.tenant_id", tenant_id)
                span.set_attribute("billing.service_id", service_id)
                span.set_attribute("billing.units_consumed", int(units_consumed))
                span.set_attribute("billing.record_outcome", "skipped")
                span.set_attribute("billing.cost", 0.0)
                span.set_attribute("billing.remaining_balance", 0.0)
                return

            span.set_attribute("billing.tenant_id", tenant_id)
            span.set_attribute("billing.service_id", service_id)
            span.set_attribute("billing.units_consumed", int(units_consumed))

            logger.info(
                "billing.cost_fallback: service=%s tier=%s cost_per_token=%s units=%s estimated_cost=%s",
                service_id,
                tier,
                cost_rate,
                units_consumed,
                float(units_consumed) * float(cost_rate),
            )

            try:
                if float(cost_rate) > 0:
                    result = await ppu.record(
                        tenant_id,
                        actor,
                        str(service_id),
                        float(units_consumed),
                        cost_per_unit=float(cost_rate),
                    )
                else:
                    result = await ppu.record(
                        tenant_id,
                        actor,
                        str(service_id),
                        float(units_consumed),
                    )
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attribute("billing.record_outcome", "failed")
                span.set_attribute("billing.cost", 0.0)
                span.set_attribute("billing.remaining_balance", 0.0)
                logger.exception("billing.record failed after inference: %s", exc)
                return

            cost = float(result.get("cost") or 0.0)
            remaining_balance = float(result.get("remaining_balance") or 0.0)
            span.set_attribute("billing.cost", cost)
            span.set_attribute("billing.remaining_balance", remaining_balance)

            if isinstance(result, dict) and result.get("error") is not None:
                span.set_attribute("billing.record_outcome", "failed")
                logger.error(
                    "billing.record: tenant=%s service=%s units=%s error=%s token_source=%s",
                    tenant_id,
                    service_id,
                    units_consumed,
                    result.get("error"),
                    token_source,
                )
                return
            if result.get("recorded") is False:
                span.set_attribute("billing.record_outcome", "failed")
                logger.warning(
                    "billing.record: tenant=%s service=%s units=%s recorded=false token_source=%s",
                    tenant_id,
                    service_id,
                    units_consumed,
                    token_source,
                )
                return

            span.set_attribute("billing.record_outcome", "recorded")
            logger.info(
                "billing.record: tenant=%s service=%s units=%s cost=%s remaining_balance=%s token_source=%s cost_rate=%s",
                tenant_id,
                service_id,
                units_consumed,
                cost,
                remaining_balance,
                token_source,
                cost_rate,
            )
    except Exception:
        logger.exception("billing.record unexpected failure — swallowed after inference")


def raise_if_ppu_denied(allowed: bool) -> None:
    """Raise HTTP 429 when pay-per-use pre-check denies the request."""
    if allowed:
        return
    raise HTTPException(
        status_code=429,
        detail={
            "error": "plan_budget_exhausted_or_quota_exceeded",
            "message": "Insufficient wallet balance or quota limit reached",
        },
    )
