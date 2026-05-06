"""Direct OpenAI-compatible proxy.

Two routes — ``POST /api/v1/chat/completions`` and ``POST /api/v1/completions`` —
resolve the upstream from ``LLM_MODEL_ENDPOINTS[body.model]`` (or
``LLM_DEFAULT_ENDPOINT``) and forward the JSON payload unchanged.

Implements 7-phase tracing lifecycle with spans: preprocess, resolve_model,
model.inference, postprocess, persist, redact (and parent inference span).
"""

import json
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from opentelemetry.trace import Status, StatusCode

from app.clients.proxy_client import InferenceProxyClient
from app.core.config import app_env
from app.tracing.llm_spans import llm_spans
from app.tracing.trace_attrs import (
    LLMAttrs,
    set_resolve_model_attrs,
    set_model_inference_attrs,
    set_postprocess_attrs,
    finalize_inference_span,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openai_proxy"])


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


async def _proxy_with_tracing(request: Request, path: str, endpoint: str) -> JSONResponse:
    payload = await _read_json_body(request)
    model = payload.get("model") if isinstance(payload, dict) else None
    user_id = getattr(request.state, "user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)

    with llm_spans.inference(
        model_name=model,
        input_count=1,
        input_type="text",
        extra_attrs={
            LLMAttrs.ENDPOINT: endpoint,
            LLMAttrs.MODEL_NAME: model or "",
        },
        user_id=user_id,
        session_id=getattr(request.state, "session_id", None),
    ) as parent_span:
        # Phase 1: preprocess (not applicable for proxy — zero-duration span)
        with llm_spans.preprocess():
            pass

        # Phase 2: resolve_model (look up upstream URL)
        url = None
        with llm_spans.resolve_model() as resolve_span:
            try:
                url = _resolve_upstream_url(model=model, path=path)
                set_resolve_model_attrs(resolve_span, model=model or "", url=url)
            except ValueError as exc:
                resolve_span.set_status(Status(StatusCode.ERROR, str(exc)))
                resolve_span.record_exception(exc)
                parent_span.set_attribute(LLMAttrs.SERVICE_STATUS, "error")
                parent_span.set_attribute("error.type", type(exc).__name__)
                return JSONResponse(status_code=503, content={"detail": str(exc)})

        # Phase 3: model.inference (forward to upstream HTTP endpoint)
        status_code, body = None, None
        with llm_spans.triton_inference() as model_span:
            try:
                status_code, body = await InferenceProxyClient().forward(
                    upstream_url=url, payload=payload
                )
                set_model_inference_attrs(
                    model_span,
                    model_name=model or "",
                    status_code=status_code,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )

                if status_code and status_code >= 400:
                    model_span.set_status(Status(StatusCode.ERROR, f"HTTP {status_code}"))
            except httpx.RequestError as exc:
                logger.warning("Upstream %s proxy failed: %s", path, exc)
                model_span.set_status(Status(StatusCode.ERROR, str(exc)))
                model_span.record_exception(exc)
                parent_span.set_attribute(LLMAttrs.SERVICE_STATUS, "error")
                parent_span.set_attribute("error.type", type(exc).__name__)
                return JSONResponse(
                    status_code=502,
                    content={"error": {"message": str(exc), "type": "upstream_error"}},
                )

        # Phase 4: postprocess (extract token usage from response)
        with llm_spans.postprocess() as post_span:
            if isinstance(body, dict):
                usage = body.get("usage")
                set_postprocess_attrs(post_span, usage=usage)

        # Phase 5: persist (not applicable for proxy — zero-duration span)
        with llm_spans.persist():
            pass

        # Finalize parent span with status
        finalize_inference_span(
            parent_span,
            status_code=status_code,
            user_id=user_id,
            tenant_id=tenant_id,
        )

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
