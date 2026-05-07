"""Direct OpenAI-compatible proxy.

Two routes — ``POST /api/v1/chat/completions`` and ``POST /api/v1/completions`` —
resolve the upstream from ``LLM_MODEL_ENDPOINTS[body.model]`` (or
``LLM_DEFAULT_ENDPOINT``) and forward the JSON payload unchanged.

When ``LLM_PPU_ENABLED=true``, runs the same pay-per-use check/record path as
``/api/v1/llm/inference`` so usage and wallet totals update for dashboard calls.

Implements 7-phase tracing lifecycle with spans: llm.preprocess, llm.resolve_model,
llm.model_inference (Phase 3 model call via custom tracer), llm.postprocess, llm.persist
(and parent llm.inference span).
"""

import json
import logging
from typing import Any, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, get_current_span

from app.clients.proxy_client import InferenceProxyClient
from app.core.config import app_env
from app.dependencies.auth import AuthProvider
from app.dependencies.llm_tenant import enforce_llm_checks
from app.tracing.llm_spans import llm_spans
from app.tracing.trace_attrs import (
    LLMAttrs,
    set_preprocess_attrs,
    set_resolve_model_attrs,
    set_model_inference_attrs,
    set_postprocess_attrs,
    finalize_inference_span,
)
from utils.llm_pay_per_use import _llm_ppu_check, _llm_ppu_record, raise_if_ppu_denied

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["openai_proxy"],
    dependencies=[Depends(AuthProvider), Depends(enforce_llm_checks)],
)


def _resolve_upstream_url(model: Optional[str], path: str) -> str:
    base = (app_env.llm_model_endpoints or {}).get(model) if model else None
    base = (base or app_env.llm_default_endpoint or "").strip()
    if not base:
        raise ValueError(
            "No upstream endpoint configured. Set LLM_MODEL_ENDPOINTS for the requested "
            "model or LLM_DEFAULT_ENDPOINT as a fallback."
        )
    return f"{base.rstrip('/')}{path}"


async def _read_json_body(request: Request) -> Any:
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc


def _openai_input_texts_for_ppu(payload: Any, upstream_path: str) -> List[str]:
    """Build text list for PPU pre-estimate (same heuristics as inference input length)."""
    if not isinstance(payload, dict):
        return [""]

    if "chat" in upstream_path:
        texts: List[str] = []
        for msg in payload.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                texts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "text":
                        t = part.get("text")
                        if isinstance(t, str) and t.strip():
                            texts.append(t)
        return texts if texts else [""]

    # /v1/completions
    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        return [prompt] if prompt else [""]
    if isinstance(prompt, list):
        out = [str(p) for p in prompt if str(p).strip()]
        return out if out else [""]
    return [""]


def _setup_inference_context(request: Request) -> dict:
    """Extract user context from request state."""
    return {
        "user_id": getattr(request.state, "user_id", None),
        "tenant_id": getattr(request.state, "tenant_id", None),
        "session_id": getattr(request.state, "session_id", None),
    }


async def _setup_ppu_checks(request: Request, input_texts: List[str]) -> None:
    """Validate pay-per-use eligibility before inference."""
    allowed = await _llm_ppu_check(request, input_texts)
    raise_if_ppu_denied(allowed)


def _setup_resolve_model(model: Optional[str], path: str) -> str:
    """Resolve upstream endpoint for the model."""
    try:
        url = _resolve_upstream_url(model=model, path=path)
        logger.debug(">>> [openai_proxy] Resolved upstream URL: %s", url)
        return url
    except ValueError as exc:
        logger.debug(">>> [openai_proxy] ERROR: Failed to resolve upstream: %s", exc)
        raise


async def _proxy_with_tracing(request: Request, path: str, endpoint: str) -> JSONResponse:
    logger.debug(
        ">>> [openai_proxy] Request received: endpoint=%s, method=%s",
        endpoint,
        request.method,
    )

    # Phase 1: Business Logic Setup (separate from tracing)
    payload = await _read_json_body(request)
    model = payload.get("model") if isinstance(payload, dict) else None
    context = _setup_inference_context(request)
    user_id = context["user_id"]
    tenant_id = context["tenant_id"]
    session_id = context["session_id"]
    logger.debug(
        ">>> [openai_proxy] Parsed payload: model=%s, user_id=%s, tenant_id=%s",
        model,
        user_id,
        tenant_id,
    )

    input_texts = _openai_input_texts_for_ppu(payload, path)
    await _setup_ppu_checks(request, input_texts)

    # Phase 2: Resolve model endpoint (business logic before tracing)
    url = None
    try:
        logger.debug(
            ">>> [openai_proxy] Resolving upstream URL for model=%s, path=%s",
            model,
            path,
        )
        url = _setup_resolve_model(model=model, path=path)
    except ValueError as exc:
        logger.debug(
            ">>> [openai_proxy] ERROR: Failed to resolve upstream: %s",
            exc,
        )
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    # Phase 3: Pure Tracing (after business logic is validated)
    with llm_spans.inference(
        model_name=model,
        input_count=1,
        input_type="text",
        extra_attrs={
            LLMAttrs.ENDPOINT: endpoint,
            LLMAttrs.LLM_MODEL_NAME: model or "",
        },
        user_id=user_id,
        session_id=session_id,
    ) as parent_span:
        # Preprocess span (not applicable for proxy — zero-duration span)
        with llm_spans.preprocess() as preprocess_span:
            set_preprocess_attrs(preprocess_span, model_name=model or "")

        # Resolve model span (record the resolved URL)
        with llm_spans.resolve_model() as resolve_span:
            set_resolve_model_attrs(resolve_span, model=model or "", url=url)

        # Model inference span (forward to upstream HTTP endpoint)
        status_code, body = None, None
        tracer = trace.get_tracer("llm-service")
        with tracer.start_as_current_span("llm.model_inference") as model_span:
            try:
                status_code, body = await InferenceProxyClient().forward(
                    upstream_url=url, payload=payload
                )
                logger.debug(
                    ">>> [openai_proxy] Upstream response: status_code=%s",
                    status_code,
                )
                set_model_inference_attrs(
                    model_span,
                    model_name=model or "",
                    model_endpoint=url or "",
                    status_code=status_code,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    service_id="openai-proxy",
                )

                if status_code and status_code >= 400:
                    logger.debug(
                        ">>> [openai_proxy] ERROR: Upstream returned %s, body=%s",
                        status_code,
                        body,
                    )
                    model_span.set_status(Status(StatusCode.ERROR, f"HTTP {status_code}"))
            except httpx.RequestError as exc:
                logger.debug(
                    ">>> [openai_proxy] ERROR: Upstream request failed: %s",
                    exc,
                )
                logger.warning("Upstream %s proxy failed: %s", path, exc)
                model_span.set_status(Status(StatusCode.ERROR, str(exc)))
                model_span.record_exception(exc)
                parent_span.set_attribute(LLMAttrs.LLM_STATUS, "error")
                parent_span.set_attribute("error.type", type(exc).__name__)
                return JSONResponse(
                    status_code=502,
                    content={"error": {"message": str(exc), "type": "upstream_error"}},
                )

        # Postprocess span (extract token usage from response)
        with llm_spans.postprocess() as post_span:
            if isinstance(body, dict):
                usage = body.get("usage")
                logger.debug(
                    ">>> [openai_proxy] Phase 4 postprocess: token usage=%s",
                    usage,
                )
                set_postprocess_attrs(post_span, usage=usage)

        # Persist span (not applicable for proxy — zero-duration span)
        with llm_spans.persist():
            pass

        # Finalize parent span with status
        logger.debug(
            ">>> [openai_proxy] Finalizing span: status_code=%s, user_id=%s, tenant_id=%s",
            status_code,
            user_id,
            tenant_id,
        )
        finalize_inference_span(
            parent_span,
            status_code=status_code,
            user_id=user_id,
            tenant_id=tenant_id,
            service_id="openai-proxy",
        )

    logger.debug(
        ">>> [openai_proxy] Returning response: status_code=%s",
        status_code,
    )
    if status_code is not None and status_code < 400 and isinstance(body, dict):
        await _llm_ppu_record(request, body, input_texts)

    return JSONResponse(status_code=status_code, content=body)


@router.post("/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    return await _proxy_with_tracing(
        request, path="/v1/chat/completions", endpoint="/v1/chat/completions"
    )


@router.post("/completions")
async def completions(request: Request) -> JSONResponse:
    return await _proxy_with_tracing(
        request, path="/v1/completions", endpoint="/v1/completions"
    )
