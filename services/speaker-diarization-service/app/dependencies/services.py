"""Dependency injection factories for Speaker Diarization service."""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.clients.triton_client import SpeakerDiarizationTritonClient
from app.repositories.speaker_diarization_repository import SpeakerDiarizationRepository
from app.services.speaker_diarization_service import SpeakerDiarizationService

logger = logging.getLogger(__name__)

get_tenant_db_session = get_tenant_db_session_factory()


async def get_speaker_diarization_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> SpeakerDiarizationService:
    """Construct SpeakerDiarizationService with Triton client and repository from request state."""
    repository = SpeakerDiarizationRepository(db)

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

    triton_client = SpeakerDiarizationTritonClient(triton_endpoint, api_key=triton_api_key or None)
    return SpeakerDiarizationService(repository=repository, triton_client=triton_client, model_name=model_name)
