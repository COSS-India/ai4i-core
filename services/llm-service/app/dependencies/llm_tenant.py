"""Shared tenant + LLM subscription enforcement for inference and OpenAI proxy routes."""

from fastapi import Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks


async def enforce_llm_checks(request: Request) -> None:
    """Enforce tenant and service availability checks for LLM."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="llm",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="LLM service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect LLM service availability. Please contact your administrator",
        timeout_message="LLM service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="LLM service is temporarily unavailable. Please try again in a few minutes.",
    )
