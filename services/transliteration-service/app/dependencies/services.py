"""Dependency injection factories for Transliteration service."""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.clients.triton_client import TransliterationTritonClient
from app.repositories.transliteration_repository import TransliterationRepository
from app.services.transliteration_service import TransliterationService
from app.services.text_service import TextService

logger = logging.getLogger(__name__)

get_tenant_db_session = get_tenant_db_session_factory()


async def get_transliteration_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> TransliterationService:
    """Construct TransliterationService with Triton client and repository from request state."""
    repository = TransliterationRepository(db)
    text_service = TextService()

    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")
    model_name = getattr(request.state, "triton_model_name", None)
    service_id = getattr(request.state, "service_id", None)

    if not triton_endpoint:
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        if service_id:
            detail = (
                f"Model Management failed to resolve Triton endpoint for serviceId: {service_id}. "
                f"Please ensure the service is registered in Model Management database."
            )
            if model_mgmt_error:
                detail += f" Error: {model_mgmt_error}"
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Request must include config.serviceId. "
                "Transliteration service requires Model Management database resolution."
            ),
        )

    if not model_name or model_name == "unknown":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Model Management failed to resolve model name for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database."
            ),
        )

    # Strip http:// scheme for tritonclient (expects host:port)
    triton_url = triton_endpoint
    if triton_url.startswith(('http://', 'https://')):
        triton_url = triton_url.split('://', 1)[1]

    triton_client = TransliterationTritonClient(triton_url, api_key=triton_api_key or None)
    return TransliterationService(
        repository=repository,
        text_service=text_service,
        triton_client=triton_client,
        model_name=model_name,
    )
