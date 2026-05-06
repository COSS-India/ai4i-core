"""Shared trace attribute names and helpers for llm-service spans."""

from typing import Any, Dict, Optional


class LLMAttrs:
    """Span attribute name constants for standardization across llm-service endpoints."""

    # On llm.inference (parent span)
    ENDPOINT = "endpoint"
    SERVICE_STATUS = "service.status"
    HTTP_STATUS_CODE = "http.status_code"
    MODEL_NAME = "model_name"
    USER_ID = "user.id"
    TENANT_ID = "tenant_id"

    # On llm.resolve_model
    RESOLVE_MODEL_NAME = "model_name"
    RESOLVE_UPSTREAM = "upstream_url"

    # On llm.model.inference
    MI_STATUS_CODE = "status_code"
    MI_USER_ID = "user.id"
    MI_TENANT_ID = "tenant_id"

    # On llm.postprocess
    PROMPT_TOKENS = "output.usage.prompt_tokens"
    COMPLETION_TOKENS = "output.usage.completion_tokens"
    TOTAL_TOKENS = "output.usage.total_tokens"


def set_resolve_model_attrs(
    span: Any,
    *,
    model: Optional[str] = None,
    url: Optional[str] = None,
) -> None:
    """Set resolve_model span attributes."""
    if model:
        span.set_attribute(LLMAttrs.RESOLVE_MODEL_NAME, model)
    if url:
        span.set_attribute(LLMAttrs.RESOLVE_UPSTREAM, url)


def set_model_inference_attrs(
    span: Any,
    *,
    status_code: Optional[int] = None,
    user_id: Optional[Any] = None,
    tenant_id: Optional[Any] = None,
) -> None:
    """Set model.inference span attributes."""
    if status_code is not None:
        span.set_attribute(LLMAttrs.MI_STATUS_CODE, str(status_code))
    if user_id is not None:
        span.set_attribute(LLMAttrs.MI_USER_ID, str(user_id))
    if tenant_id is not None:
        span.set_attribute(LLMAttrs.MI_TENANT_ID, str(tenant_id))


def set_postprocess_attrs(
    span: Any,
    *,
    usage: Optional[Dict[str, Any]] = None,
) -> None:
    """Set postprocess span attributes from token usage dict."""
    if not isinstance(usage, dict):
        return
    if (v := usage.get("prompt_tokens")) is not None:
        span.set_attribute(LLMAttrs.PROMPT_TOKENS, str(v))
    if (v := usage.get("completion_tokens")) is not None:
        span.set_attribute(LLMAttrs.COMPLETION_TOKENS, str(v))
    if (v := usage.get("total_tokens")) is not None:
        span.set_attribute(LLMAttrs.TOTAL_TOKENS, str(v))


def finalize_inference_span(
    span: Any,
    *,
    status_code: Optional[int] = None,
    user_id: Optional[Any] = None,
    tenant_id: Optional[Any] = None,
) -> None:
    """Finalize inference span with status and user/tenant context."""
    span.set_attribute(LLMAttrs.HTTP_STATUS_CODE, str(status_code or ""))
    span.set_attribute(
        LLMAttrs.SERVICE_STATUS,
        "success" if (status_code and status_code < 400) else "error",
    )
    if user_id is not None:
        span.set_attribute(LLMAttrs.USER_ID, str(user_id))
    if tenant_id is not None:
        span.set_attribute(LLMAttrs.TENANT_ID, str(tenant_id))
