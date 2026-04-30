"""Dependency injection factories for Language Detection service."""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.clients.triton_client import LanguageDetectionTritonClient
from app.repositories.language_detection_repository import LanguageDetectionRepository
from app.services.text_service import TextService
from app.services.language_detection_service import LanguageDetectionService

logger = logging.getLogger(__name__)

get_tenant_db_session = get_tenant_db_session_factory()


async def get_language_detection_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> LanguageDetectionService:
    """Construct LanguageDetectionService with Triton client and repository from request state."""
    repository = LanguageDetectionRepository(db)
    text_service = TextService()

    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")
    model_name = getattr(request.state, "triton_model_name", None)
    service_id = getattr(request.state, "service_id", None)

    if not triton_endpoint:
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        if service_id:
            detail = (
                f"Model Management failed to resolve Triton endpoint for serviceId: {service_id}."
            )
            if model_mgmt_error:
                detail += f" Error: {model_mgmt_error}"
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request must include config.serviceId.",
        )

    if not model_name or model_name == "unknown":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model Management failed to resolve model name for serviceId: {service_id}.",
        )

    triton_client = LanguageDetectionTritonClient(triton_endpoint, api_key=triton_api_key or None)
    return LanguageDetectionService(
        repository=repository,
        text_service=text_service,
        triton_client=triton_client,
        model_name=model_name,
    )
