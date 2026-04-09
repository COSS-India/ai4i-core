"""Dependency injection factories for TTS service."""

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.clients.triton_client import TTSTritonClient
from app.repositories.tts_repository import TTSRepository
from app.services.audio_service import AudioService
from app.services.text_service import TextService
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)

get_tenant_db_session = get_tenant_db_session_factory()


async def get_tts_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> TTSService:
    """Construct TTSService from request state set by Model Management middleware."""
    repository = TTSRepository(db)
    audio_service = AudioService()
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
                "TTS service requires Model Management database resolution."
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

    # Strip protocol prefix from endpoint URL
    triton_url = triton_endpoint
    if triton_url.startswith(("http://", "https://")):
        triton_url = triton_url.split("://", 1)[1]

    triton_client = TTSTritonClient(triton_url=triton_url, api_key=triton_api_key)

    return TTSService(
        repository=repository,
        audio_service=audio_service,
        text_service=text_service,
        triton_client=triton_client,
        resolved_model_name=model_name,
    )
