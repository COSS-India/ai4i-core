"""
Inference router for NER service.

Exposes a ULCA-style NER inference endpoint:
- POST /api/v1/ner/inference
"""

import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

from models.ner_request import NerInferenceRequest
from models.ner_response import NerInferenceResponse, NerPrediction, NerTokenPrediction
from services.ner_service import NerService, TritonInferenceError
from repositories.ner_repository import NERRepository
from utils.triton_client import TritonClient
from middleware.auth_provider import AuthProvider
from ai4icore_multi_tenant import (
    get_tenant_db_session_factory,
    try_get_tenant_context,
    enforce_tenant_and_service_checks,
)

get_tenant_db_session = get_tenant_db_session_factory()
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from ai4icore_env import app_env
from ai4icore_constants.exceptions import ErrorDetail
from fastapi import Depends

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("ner-service")

inference_router = APIRouter(
    prefix="/api/v1/ner",
    tags=["NER Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)

#Tenant routing and service checks
API_GATEWAY_URL = app_env.api_gateway_url


async def enforce_ner_checks(request: Request):
    """FastAPI dependency that enforces tenant and service checks for NER before other dependencies run."""
    # the service name is coming from multitenant SubscriptionType enum
    await enforce_tenant_and_service_checks(
        request,
        service_name="ner",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="NER service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect NER service availability. Please contact your administrator",
        timeout_message="NER service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="NER service is temporarily unavailable. Please try again in a few minutes.",
    )

# Add as a router-level dependency so it runs before path-operation dependencies like get_ner_service
inference_router.dependencies.append(Depends(enforce_ner_checks))


async def get_ner_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session),
) -> NerService:
    """
    Dependency to construct NerService with configured Triton client and repository.

    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = NERRepository(db)
    
    # Get middleware-resolved endpoint from Model Management database
    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")
    
    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        
        if service_id:
            error_detail = (
                f"Model Management failed to resolve Triton endpoint for serviceId: {service_id}. "
                f"Please ensure the service is registered in Model Management database."
            )
            if model_mgmt_error:
                error_detail += f" Error: {model_mgmt_error}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Request must include config.serviceId. "
                "NER service requires Model Management database resolution."
            ),
        )
    
    # Get resolved model name from middleware (MUST be resolved by Model Management)
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Model Management failed to resolve Triton model name for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            ),
        )
    
    logger.info(
        f"Using endpoint={triton_endpoint} model_name={model_name} from Model Management "
        f"for serviceId={getattr(request.state, 'service_id', 'unknown')}"
    )
    
    # Create NER-specific TritonClient (has NER-specific methods like get_ner_io_for_triton)
    triton_client = TritonClient(triton_endpoint, triton_api_key or None)
    return NerService(repository=repository, triton_client=triton_client, model_name=model_name)


@inference_router.post(
    "/inference",
    response_model=NerInferenceResponse,
    summary="Perform batch NER inference",
    description="Run NER on one or more text inputs via Triton.",
    dependencies=[Depends(AuthProvider)],  # Explicitly enforce auth at endpoint level (in addition to router-level)
)
async def run_inference(
    request_body: NerInferenceRequest,
    http_request: Request,
    ner_service: NerService = Depends(get_ner_service),
) -> NerInferenceResponse:
    """
    Run NER inference for a batch of text inputs.
    
    Creates detailed trace spans for the entire inference operation.
    
    The Model Resolution Middleware automatically resolves serviceId from
    request_body.config.serviceId to triton_endpoint and model_name,
    which are available in http_request.state.
    """
    if not tracer:
        # Fallback if tracing not available
        return await _run_ner_inference_impl(request_body, http_request, ner_service)
    
    with tracer.start_as_current_span("ner.inference") as span:
        try:
            # -----------------------------
            # Authentication context span
            # -----------------------------
            with tracer.start_as_current_span("ner.auth_context") as auth_span:
                # Extract auth context from request.state (set by AuthProvider middleware)
                user_id = getattr(http_request.state, "user_id", None)
                api_key_id = getattr(http_request.state, "api_key_id", None)
                session_id = getattr(http_request.state, "session_id", None)

                # Header-level auth signals
                has_bearer_header = bool(http_request.headers.get("authorization"))
                has_api_key_header = "x-api-key" in {k.lower(): v for k, v in http_request.headers.items()}

                auth_span.set_attribute("auth.user_id", str(user_id) if user_id is not None else "")
                auth_span.set_attribute("auth.api_key_id", str(api_key_id) if api_key_id is not None else "")
                auth_span.set_attribute("auth.session_id", str(session_id) if session_id is not None else "")
                auth_span.set_attribute("auth.has_bearer_header", has_bearer_header)
                auth_span.set_attribute("auth.has_api_key_header", has_api_key_header)
                auth_span.set_attribute(
                    "auth.is_authenticated",
                    bool(user_id is not None or api_key_id is not None),
                )
            
            # Get correlation ID for log/trace correlation (shared across auth + inference)
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)

            # Add request metadata to span
            span.set_attribute("ner.input_count", len(request_body.input))
            span.set_attribute("ner.service_id", request_body.config.serviceId)
            span.set_attribute("ner.language", request_body.config.language.sourceLanguage)
            
            # Track request size (approximate)
            try:
                request_size = len(json.dumps(request_body.dict()).encode('utf-8'))
                span.set_attribute("http.request.size_bytes", request_size)
            except Exception:
                pass
            
            if user_id:
                span.set_attribute("user.id", str(user_id))
            if api_key_id:
                span.set_attribute("api_key.id", str(api_key_id))
            if session_id:
                span.set_attribute("session.id", str(session_id))
            
            # Add span event for request start
            span.add_event("ner.inference.started", {
                "input_count": len(request_body.input),
                "service_id": request_body.config.serviceId,
                "language": request_body.config.language.sourceLanguage
            })

            logger.info(
                "Processing NER inference request with %d text input(s), "
                "user_id=%s api_key_id=%s session_id=%s",
                len(request_body.input),
                user_id,
                api_key_id,
                session_id,
            )

            response = await ner_service.run_inference(
                request_body,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            
            # Add response metadata
            span.set_attribute("ner.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("ner.inference.completed", {
                "output_count": len(response.output),
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            logger.info("NER inference completed successfully")
            return response

        except ValueError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("ner.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in NER inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except TritonInferenceError as exc:
            try:
                from ai4icore_constants.static_fallback_responses import (
                    is_static_fallback_enabled,
                    get_ner_static_response,
                )
            except Exception:
                # If the shared constants package is not available in this
                # runtime (e.g. not copied into the image or import is
                # shadowed), gracefully disable static fallback rather than
                # failing the entire request with an import error.
                def is_static_fallback_enabled() -> bool:  # type: ignore[no-redef]
                    return False

                get_ner_static_response = None  # type: ignore[assignment]

            if is_static_fallback_enabled():
                input_texts = [inp.source for inp in request_body.input]
                static_data = (
                    get_ner_static_response(input_texts)
                    if get_ner_static_response is not None
                    else None
                )
                if static_data is None:
                    raise
                output = []
                for item in static_data["output"]:
                    predictions = [
                        NerTokenPrediction(**p) for p in item["nerPrediction"]
                    ]
                    output.append(NerPrediction(source=item["source"], nerPrediction=predictions))
                span.add_event("ner.inference.static_fallback", {"reason": "Triton unreachable"})
                span.set_status(Status(StatusCode.OK))
                logger.info("Returning static NER fallback (Triton unreachable)")
                return NerInferenceResponse(output=output)
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 503)
            if service_id:
                span.set_attribute("ner.service_id", service_id)
            if triton_endpoint:
                span.set_attribute("triton.endpoint", triton_endpoint)
            if model_name:
                span.set_attribute("triton.model_name", model_name)
            span.add_event("ner.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
            error_detail = (
                f"NER inference failed for serviceId '{service_id}' "
                f"at endpoint '{triton_endpoint}' with model '{model_name}': {str(exc)}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
            
            logger.error(
                "NER Triton inference failed: %s (serviceId=%s, endpoint=%s, model=%s)",
                exc, service_id, triton_endpoint, model_name
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_detail,
            ) from exc
        except Exception as exc:  # pragma: no cover - generic error path
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)
            if service_id:
                span.set_attribute("ner.service_id", service_id)
            if triton_endpoint:
                span.set_attribute("triton.endpoint", triton_endpoint)
            if model_name:
                span.set_attribute("triton.model_name", model_name)
            span.add_event("ner.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
            error_detail = str(exc)
            
            # Include model management context in error message
            if service_id and triton_endpoint:
                error_detail = (
                    f"NER inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                    "Please verify the model is registered in Model Management and the Triton server is accessible."
                )
            elif service_id:
                error_detail = (
                    f"NER inference failed for serviceId '{service_id}': {error_detail}. "
                    "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
                )
            else:
                error_detail = (
                    f"NER inference failed: {error_detail}. "
                    "Please ensure config.serviceId is provided and the service is registered in Model Management."
                )
            
            logger.error(
                "NER inference failed: %s (serviceId=%s, endpoint=%s)",
                exc, service_id, triton_endpoint, exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            ) from exc


async def _run_ner_inference_impl(
    request_body: NerInferenceRequest,
    http_request: Request,
    ner_service: NerService,
) -> NerInferenceResponse:
    """Fallback implementation when tracing is not available."""
    from ai4icore_constants.static_fallback_responses import (
        is_static_fallback_enabled,
        get_ner_static_response,
    )
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    logger.info(
        "Processing NER inference request with %d text input(s), "
        "user_id=%s api_key_id=%s session_id=%s",
        len(request_body.input),
        user_id,
        api_key_id,
        session_id,
    )

    try:
        response = await ner_service.run_inference(
            request_body,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        logger.info("NER inference completed successfully")
        return response
    except TritonInferenceError as exc:
        if is_static_fallback_enabled():
            input_texts = [inp.source for inp in request_body.input]
            static_data = get_ner_static_response(input_texts)
            output = []
            for item in static_data["output"]:
                predictions = [NerTokenPrediction(**p) for p in item["nerPrediction"]]
                output.append(NerPrediction(source=item["source"], nerPrediction=predictions))
            logger.info("Returning static NER fallback (Triton unreachable)")
            return NerInferenceResponse(output=output)
        logger.error("NER Triton inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc



