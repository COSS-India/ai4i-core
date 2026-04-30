"""Dependency injection factories for Language Diarization service."""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.clients.triton_client import LanguageDiarizationTritonClient
from app.repositories.language_diarization_repository import LanguageDiarizationRepository
from app.services.language_diarization_service import LanguageDiarizationService

logger = logging.getLogger(__name__)

get_tenant_db_session = get_tenant_db_session_factory()


async def get_language_diarization_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> LanguageDiarizationService:
    """Construct LanguageDiarizationService with Triton client and repository from request state."""
    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")
    triton_timeout = getattr(request.app.state, "triton_timeout", 300.0)
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

    triton_client = LanguageDiarizationTritonClient(
        triton_endpoint, api_key=triton_api_key or None, timeout=triton_timeout
    )
    repository = LanguageDiarizationRepository(db)
    return LanguageDiarizationService(triton_client=triton_client, repository=repository)
