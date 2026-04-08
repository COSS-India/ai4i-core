"""Dependency injection factories for NMT service."""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.clients.triton_client import NMTTritonClient
from app.repositories.nmt_repository import NMTRepository
from app.services.text_service import TextService
from app.services.nmt_service import NMTService

logger = logging.getLogger(__name__)

get_tenant_db_session = get_tenant_db_session_factory()


async def get_nmt_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> NMTService:
    """Construct NMTService from request state set by Model Management middleware.

    For context-aware requests (LLM bypass), a minimal service is returned because
    the Triton path is skipped entirely.
    """
    # Context-aware requests skip Triton -- return a minimal service instance
    is_context_aware = getattr(request.state, "is_context_aware", False)
    if is_context_aware:
        logger.info("Context-aware request detected, skipping NMTService Triton initialisation")
        repository = NMTRepository(db)
        return NMTService(repository=repository, text_service=None)

    repository = NMTRepository(db)
    text_service = TextService()

    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.state, "triton_api_key", None)
    model_name = getattr(request.state, "triton_model_name", None)
    service_id = getattr(request.state, "service_id", None)

    if not triton_endpoint:
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        smr_response_data = getattr(request.state, "smr_response_data", None)

        if service_id:
            error_msg = (
                f"Model Management did not resolve serviceId: {service_id} "
                "and no default endpoint is allowed. "
                "Please ensure the service is registered in Model Management database."
            )
            if model_mgmt_error:
                error_msg += f" Error: {model_mgmt_error}"

            error_detail = {
                "code": "ENDPOINT_RESOLUTION_FAILED",
                "message": error_msg,
                "smr_response": smr_response_data,
            }
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Request must include config.serviceId. "
                "NMT service requires Model Management database resolution."
            ),
        )

    if not model_name or model_name == "unknown":
        smr_response_data = getattr(request.state, "smr_response_data", None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "MODEL_NAME_RESOLUTION_FAILED",
                "message": (
                    f"Model Management did not resolve model name for serviceId: {service_id}. "
                    "Please ensure the model is properly configured in Model Management database "
                    "with inference endpoint schema."
                ),
                "smr_response": smr_response_data,
            },
        )

    # Factory function to create Triton clients for different endpoints
    def get_triton_client_for_endpoint(endpoint: str) -> NMTTritonClient:
        return NMTTritonClient(triton_url=endpoint, api_key=triton_api_key)

    redis_client = getattr(request.app.state, "redis_client", None)
    model_management_client = getattr(request.app.state, "model_management_client", None)

    if not model_management_client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Model Management client not available. Service configuration error.",
        )

    cache_ttl_seconds = getattr(model_management_client, "cache_ttl_seconds", 300)
    pii_url = getattr(request.app.state, "pii_service_url", None)
    pii_timeout = float(getattr(request.app.state, "pii_redact_timeout", 20.0))
    pii_http_client = getattr(request.app.state, "pii_http_client", None)

    return NMTService(
        repository=repository,
        text_service=text_service,
        get_triton_client_func=get_triton_client_for_endpoint,
        model_management_client=model_management_client,
        redis_client=redis_client,
        cache_ttl_seconds=cache_ttl_seconds,
        pii_redact_base_url=pii_url,
        pii_redact_timeout=pii_timeout,
        pii_http_client=pii_http_client,
    )
