"""NER inference endpoint."""

import logging

from fastapi import APIRouter, Depends, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_ner_service
from app.schemas.inference import NerInferenceRequest, NerInferenceResponse
from app.services.ner_service import NerService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/ner",
    tags=["NER Inference"],
    dependencies=[Depends(AuthProvider)],
)


async def enforce_ner_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="ner",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="NER service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect NER service availability. Please contact your administrator",
        timeout_message="NER service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="NER service is temporarily unavailable. Please try again in a few minutes.",
    )


router.dependencies.append(Depends(enforce_ner_checks))


@router.post("/inference", response_model=NerInferenceResponse)
async def run_inference(
    request_body: NerInferenceRequest,
    http_request: Request,
    ner_service: NerService = Depends(get_ner_service),
) -> NerInferenceResponse:
    """Run NER inference for a batch of text inputs."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    return await ner_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
    )
