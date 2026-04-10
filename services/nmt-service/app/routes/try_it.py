"""
Try-It Router
FastAPI router for anonymous try-it endpoint (migrated from API gateway).
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory
from ai4icore_constants.error_messages import SERVICE_UNPUBLISHED, SERVICE_UNPUBLISHED_MESSAGE

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_nmt_service
from app.schemas.inference import (
    NMTInferenceRequest,
    NMTInferenceResponse,
    TranslationOutput,
    TryItRequest,
)
from app.services.smr_service import SMRService

from app.utils.try_it_utils import get_try_it_key, increment_try_it_count, is_try_it_rate_limit_exceeded
from app.utils.auth_utils import extract_auth_headers

logger = logging.getLogger(__name__)

get_tenant_db_session = get_tenant_db_session_factory()
smr_service = SMRService()

router = APIRouter(
    prefix="/api/v1",
    tags=["Try It"],
    dependencies=[Depends(AuthProvider)],
)


@router.post("/try-it", response_model=Dict[str, Any])
async def try_it_inference(
    payload: TryItRequest,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> Dict[str, Any]:
    """Anonymous Try-It access for NMT. Supports rate-limited anonymous and authenticated access."""

    # ── Validate service name ──
    service_name = payload.service_name.strip().lower()
    if service_name not in {"nmt", "nmt-service"}:
        raise HTTPException(status_code=403, detail="Please login to access other services.")

    # ── Auth / rate-limit ──
    is_authenticated = getattr(request.state, "is_authenticated", False)
    user_id = getattr(request.state, "user_id", None)
    api_key_id = getattr(request.state, "api_key_id", None)

    if not is_authenticated:
        redis_client = getattr(request.app.state, "redis_client", None)
        key = get_try_it_key(request)
        count = await increment_try_it_count(key, redis_client)
        if is_try_it_rate_limit_exceeded(count):
            logger.warning("Try-it rate limit exceeded", extra={"key": key, "count": count})
            raise HTTPException(status_code=403, detail="Please login to access other services.")

    # ── Parse inner payload ──
    try:
        nmt_request = NMTInferenceRequest(**payload.payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload format: {e}")

    # ── Default service for anonymous ──
    if not is_authenticated and not nmt_request.config.serviceId:
        nmt_request.config.serviceId = "ai4bharat/indictrans--gpu-t4"

    request.state.service_id = nmt_request.config.serviceId

    # ── Resolve endpoint via Model Management ──
    model_management_client = getattr(request.app.state, "model_management_client", None)
    redis_client = getattr(request.app.state, "redis_client", None)

    if model_management_client and nmt_request.config.serviceId:
        try:
            auth_headers = {"X-Try-It": "true"}
            service_info = await model_management_client.get_service(
                service_id=nmt_request.config.serviceId,
                use_cache=True,
                redis_client=redis_client,
                auth_headers=auth_headers,
            )
            if service_info and service_info.endpoint:
                if service_info.is_published is not True:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": SERVICE_UNPUBLISHED,
                            "message": SERVICE_UNPUBLISHED_MESSAGE,
                            "serviceId": nmt_request.config.serviceId,
                        },
                    )
                request.state.triton_endpoint = service_info.endpoint
                request.state.triton_api_key = service_info.api_key or ""

                triton_model_name = _extract_model_name(service_info)
                request.state.triton_model_name = triton_model_name
            else:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "ENDPOINT_RESOLUTION_FAILED",
                        "message": f"Service {nmt_request.config.serviceId} not found or has no endpoint.",
                        "service_id": nmt_request.config.serviceId,
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "ENDPOINT_RESOLUTION_FAILED",
                    "message": f"Failed to resolve endpoint for serviceId {nmt_request.config.serviceId}: {e}",
                    "service_id": nmt_request.config.serviceId,
                },
            ) from e

    # ── Optional SMR for authenticated users ──
    smr_response = None
    if is_authenticated:
        try:
            smr_response = await smr_service.resolve_service_id(nmt_request, request)
        except Exception as e:
            logger.warning("SMR call failed for try-it, continuing with provided serviceId: %s", e)

    nmt_service = await get_nmt_service(request, db)

    # ── Context-aware short-circuit ──
    if smr_response and smr_response.get("context_aware_result"):
        context_output = smr_response.get("context_aware_result", {}).get("output", [])
        output_list = [
            TranslationOutput(source=item.get("source", ""), target=item.get("target", ""))
            for item in context_output
        ]
        response = NMTInferenceResponse(output=output_list, smr_response=smr_response)
        return response.dict()

    # ── Run inference ──
    session_id = getattr(request.state, "session_id", None)
    response = await nmt_service.run_inference(
        request=nmt_request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
        auth_headers=extract_auth_headers(request),
        http_request=request,
    )

    response_dict = response.dict()
    response_dict["smr_response"] = smr_response
    return response_dict


def _extract_model_name(service_info) -> str:
    """Extract triton model name from service info."""
    if service_info.model_inference_endpoint:
        ie = service_info.model_inference_endpoint
        if isinstance(ie, dict):
            return (
                ie.get("model_name")
                or ie.get("modelName")
                or ie.get("model")
                or service_info.triton_model
                or service_info.model_name
                or "unknown"
            )
    if service_info.model_name:
        return service_info.model_name
    if service_info.triton_model:
        return service_info.triton_model
    return "unknown"
