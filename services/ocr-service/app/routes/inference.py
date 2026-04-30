"""OCR inference endpoint."""

import logging

from fastapi import APIRouter, Depends, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_ocr_service
from app.schemas.inference import OCRInferenceRequest, OCRInferenceResponse
from app.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/ocr",
    tags=["OCR Inference"],
    dependencies=[Depends(AuthProvider)],
)


async def enforce_ocr_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="ocr",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="OCR service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect OCR service availability. Please contact your administrator",
        timeout_message="OCR service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="OCR service is temporarily unavailable. Please try again in a few minutes.",
    )


router.dependencies.append(Depends(enforce_ocr_checks))


@router.post("/inference", response_model=OCRInferenceResponse)
async def run_inference(
    request_body: OCRInferenceRequest,
    http_request: Request,
    ocr_service: OCRService = Depends(get_ocr_service),
) -> OCRInferenceResponse:
    """Run OCR inference for a batch of images."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    return await ocr_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
    )
