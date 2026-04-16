"""Dependency injection factories for ASR service."""

import logging
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory
from ai4icore_exceptions import ErrorDetail
from ai4icore_constants.error_messages import (
    MODEL_UNAVAILABLE,
    MODEL_UNAVAILABLE_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_MESSAGE,
)

from app.clients.triton_client import ASRTritonClient
from app.repositories.asr_repository import ASRRepository
from app.services.asr_service import ASRService
from app.services.audio_service import AudioService

logger = logging.getLogger(__name__)

get_tenant_db_session = get_tenant_db_session_factory()


async def get_asr_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> ASRService:
    """Construct ASRService with Triton client and repository from request state.

    REQUIRES Model Management database resolution -- no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = ASRRepository(db)
    audio_service = AudioService()

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
            error_detail = ErrorDetail(message=MODEL_UNAVAILABLE_MESSAGE, code=MODEL_UNAVAILABLE)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail.dict())
        error_detail = ErrorDetail(message=INVALID_REQUEST_MESSAGE, code=INVALID_REQUEST)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail.dict())

    if not model_name or model_name == "unknown":
        error_detail = ErrorDetail(message=MODEL_UNAVAILABLE_MESSAGE, code=MODEL_UNAVAILABLE)
        logger.error(
            "Model Management failed to resolve Triton model name for serviceId: %s",
            service_id,
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail.dict())

    logger.info(
        "Using Triton endpoint=%s model_name=%s for serviceId=%s from Model Management",
        triton_endpoint,
        model_name,
        service_id,
    )

    triton_client = ASRTritonClient(triton_endpoint, api_key=triton_api_key or None)
    return ASRService(
        repository=repository,
        audio_service=audio_service,
        triton_client=triton_client,
        resolved_model_name=model_name,
    )
