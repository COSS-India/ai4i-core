"""NMT inference endpoint."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks
from ai4icore_constants.error_messages import SERVICE_UNAVAILABLE

from utils.nmt_pay_per_use import (
    _effective_service_id_for_ppu,
    _nmt_ppu_check,
    _nmt_ppu_record,
)

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_nmt_service
from app.schemas.inference import NMTInferenceRequest, NMTInferenceResponse, TranslationOutput
from app.services.nmt_service import NMTService
from app.services.smr_service import SMRService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT Inference"],
    dependencies=[Depends(AuthProvider)],
)

smr_service = SMRService()


async def enforce_nmt_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="nmt",
        service_unavailable_code=SERVICE_UNAVAILABLE,
        service_inactive_message="NMT service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect NMT service availability. Please contact your administrator",
        timeout_message="NMT service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="NMT service is temporarily unavailable. Please try again in a few minutes.",
    )


router.dependencies.append(Depends(enforce_nmt_checks))


async def resolve_service_id_if_needed(
    request: NMTInferenceRequest,
    http_request: Request,
) -> Optional[Dict[str, Any]]:
    """Dependency: resolve serviceId via SMR when not provided."""
    return await smr_service.resolve_service_id(request, http_request)


@router.post("/inference", response_model=NMTInferenceResponse)
async def run_inference(
    request: NMTInferenceRequest,
    http_request: Request,
    smr_response: Optional[Dict[str, Any]] = Depends(resolve_service_id_if_needed),
    nmt_service: NMTService = Depends(get_nmt_service),
) -> NMTInferenceResponse:
    """Run NMT inference on the given request."""

    # ── Context-aware short-circuit ──
    if smr_response and smr_response.get("context_aware_result"):
        logger.info("NMT inference: Using context-aware result from SMR")
        context_output = smr_response.get("context_aware_result", {}).get("output", [])
        sid_ctx = _effective_service_id_for_ppu(
            http_request,
            request.config.serviceId,
            smr_response.get("serviceId"),
        )
        if request.input:
            nmt_ppu_units_ctx = float(max(sum(len(inp.source or "") for inp in request.input), 1))
        else:
            nmt_ppu_units_ctx = float(
                max(
                    sum(
                        len(str(item.get("source", "") or ""))
                        + len(str(item.get("target", "") or ""))
                        for item in context_output
                    ),
                    1,
                )
            )
        await _nmt_ppu_check(http_request, sid_ctx, nmt_ppu_units_ctx)
        output_list = [
            TranslationOutput(source=item.get("source", ""), target=item.get("target", ""))
            for item in context_output
        ]
        response = NMTInferenceResponse(output=output_list, smr_response=smr_response)
        await _nmt_ppu_record(http_request, sid_ctx, nmt_ppu_units_ctx)
        return response

    # ── Context-aware guard (no result but header was set) ──
    context_aware_header = http_request.headers.get("X-Context-Aware") or http_request.headers.get("x-context-aware")
    is_context_aware = bool(
        context_aware_header and context_aware_header.strip().lower() in {"1", "true", "yes", "y"}
    )
    if is_context_aware and not request.config.serviceId and (
        not smr_response or not smr_response.get("context_aware_result")
    ):
        raise HTTPException(
            status_code=500,
            detail={
                "code": "CONTEXT_AWARE_ERROR",
                "message": "Context-aware routing was requested but failed to return a result. Please check SMR service logs.",
                "smr_response": smr_response,
            },
        )

    # ── Extract auth context ──
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    input_texts = [inp.source for inp in request.input]
    total_input_characters = sum(len(text or "") for text in input_texts)
    smr_for_ppu = smr_response or getattr(http_request.state, "smr_response_data", None)
    sid_ppu = _effective_service_id_for_ppu(
        http_request,
        request.config.serviceId,
        smr_for_ppu.get("serviceId") if smr_for_ppu else None,
    )
    await _nmt_ppu_check(
        http_request,
        sid_ppu,
        float(max(total_input_characters, 1)),
    )

    # ── Run inference (fallback retry handled inside nmt_service) ──
    response = await nmt_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
        http_request=http_request,
    )

    # ── Attach SMR metadata ──
    smr_response_data = smr_response or getattr(http_request.state, "smr_response_data", None)
    sid_record = _effective_service_id_for_ppu(
        http_request,
        request.config.serviceId,
        smr_response_data.get("serviceId") if smr_response_data else None,
    )
    await _nmt_ppu_record(
        http_request,
        sid_record,
        float(max(total_input_characters, 1)),
    )

    response_dict = response.dict()
    response_dict["smr_response"] = smr_response_data
    return NMTInferenceResponse(**response_dict)
