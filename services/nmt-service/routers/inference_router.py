"""
Inference Router
FastAPI router for NMT inference endpoints
"""

import logging
import time
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

from models.nmt_request import NMTInferenceRequest
from models.nmt_response import NMTInferenceResponse
from repositories.nmt_repository import NMTRepository
from services.nmt_service import NMTService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.auth_utils import extract_auth_headers
from utils.validation_utils import (
    validate_language_pair, validate_service_id, validate_batch_size,
    InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError
)
from middleware.auth_provider import AuthProvider
from middleware.exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("nmt-service")

# Create router
inference_router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session"""
    return request.app.state.db_session_factory()


async def get_nmt_service(request: Request, db: AsyncSession = Depends(get_db_session)) -> NMTService:
    """
    Dependency to get configured NMT service.
    
    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = NMTRepository(db)
    text_service = TextService()
    
    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.state, "triton_api_key", None)
    
    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        
        if service_id:
            error_detail = (
                f"Model Management did not resolve serviceId: {service_id} and no default endpoint is allowed. "
                f"Please ensure the service is registered in Model Management database."
            )
            if model_mgmt_error:
                error_detail += f" Error: {model_mgmt_error}"
            raise HTTPException(
                status_code=500,
                detail=error_detail,
            )
        raise HTTPException(
            status_code=400,
            detail=(
                "Request must include config.serviceId. "
                "NMT service requires Model Management database resolution."
            ),
        )
    
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Model Management did not resolve model name for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            ),
        )
    
    logger.info(
        "Using Triton endpoint=%s model_name=%s for serviceId=%s from Model Management",
        triton_endpoint,
        model_name,
        getattr(request.state, "service_id", "unknown"),
    )
    
    # Factory function to create Triton clients for different endpoints
    def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
        """Create Triton client for specific endpoint"""
        # Strip http:// or https:// scheme from URL if present
        triton_url = endpoint
        if triton_url.startswith(('http://', 'https://')):
            triton_url = triton_url.split('://', 1)[1]
        return TritonClient(
            triton_url=triton_url,
            api_key=triton_api_key
        )
    
    # Get Redis client and Model Management client from app state
    redis_client = getattr(request.app.state, "redis_client", None)
    model_management_client = getattr(request.app.state, "model_management_client", None)
    
    if not model_management_client:
        raise HTTPException(
            status_code=500,
            detail="Model Management client not available. Service configuration error."
        )
    
    # Get cache TTL from Model Management client config
    cache_ttl_seconds = getattr(model_management_client, "cache_ttl_seconds", 300)
    
    return NMTService(
        repository=repository, 
        text_service=text_service,
        get_triton_client_func=get_triton_client_for_endpoint,
        model_management_client=model_management_client,
        redis_client=redis_client,
        cache_ttl_seconds=cache_ttl_seconds
    )


@inference_router.post(
    "/inference",
    response_model=NMTInferenceResponse,
    summary="Perform batch NMT inference",
    description="Translate text from source language to target language for one or more text inputs (max 90)"
)
async def run_inference(
    request: NMTInferenceRequest,
    http_request: Request,
    nmt_service: NMTService = Depends(get_nmt_service)
) -> NMTInferenceResponse:
    """Run NMT inference on the given request"""
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_inference_impl(request, http_request, nmt_service)
    
    # Business-level span: Main NMT request processing
    with tracer.start_as_current_span("NMT Request Processing") as span:
        span.set_attribute("purpose", "Processes NMT requests for translating text between languages")
        span.set_attribute("user_visible", True)
        span.set_attribute("impact_if_slow", "User waits longer for translated text to appear")
        span.set_attribute("owner", "Language AI Platform")
        
        try:
            # Validate request
            validate_service_id(request.config.serviceId)
            validate_language_pair(
                request.config.language.sourceLanguage,
                request.config.language.targetLanguage
            )
            validate_batch_size(len(request.input))
            
            # Extract auth context from request.state
            user_id = getattr(http_request.state, 'user_id', None)
            api_key_id = getattr(http_request.state, 'api_key_id', None)
            session_id = getattr(http_request.state, 'session_id', None)
            
            # Get correlation ID for log/trace correlation
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)
            
            # Add request metadata to span (keep technical details as attributes)
            span.set_attribute("nmt.input_count", len(request.input))
            span.set_attribute("nmt.service_id", request.config.serviceId)
            span.set_attribute("nmt.source_language", request.config.language.sourceLanguage)
            span.set_attribute("nmt.target_language", request.config.language.targetLanguage)
            
            # Store first input text for UI display (truncate if too long)
            if request.input and len(request.input) > 0 and request.input[0].source:
                first_input = request.input[0].source.strip()
                # Store up to 500 characters to avoid huge span attributes
                if len(first_input) > 500:
                    span.set_attribute("nmt.input_text", first_input[:500] + "...")
                else:
                    span.set_attribute("nmt.input_text", first_input)
            
            if user_id:
                span.set_attribute("user.id", str(user_id))
            if api_key_id:
                span.set_attribute("api_key.id", str(api_key_id))
            if session_id:
                span.set_attribute("session.id", str(session_id))
            
            # Business-level span: Context & Policy Evaluation
            # Collapsed: Identity context and policy checks are now combined into one business step
            with tracer.start_as_current_span("Context & Policy Evaluation") as context_span:
                context_span.set_attribute("purpose", "Evaluates user context, policies, and routing decisions before processing translation")
                context_span.set_attribute("user_visible", False)
                context_span.set_attribute("impact_if_slow", "Request is delayed - user may experience slower response times")
                context_span.set_attribute("owner", "Platform Team")
                
                # Simulated Future Functionality Logging
                identity_context = {
                    "Identity Details": {
                        "Tenant": "Ministry of Education",
                        "Budget": "₹50,000",
                        "Daily Quota": "10,000",
                        "Data Tier": "Sensitive"
                    },
                    "Contract Loaded": {
                        "Channel": "Web Portal",
                        "Use Case": "Policy Translation",
                        "Sensitivity": "High",
                        "Languages": ["Hindi", "English"],
                        "SLA": "< 5s"
                    },
                    "Runtime Analysis": {
                        "Language": f"{request.config.language.sourceLanguage} → {request.config.language.targetLanguage}"
                    }
                }
                
                logger.info(
                    "Identity & Context Attached",
                    extra={
                        "event_type": "identity_context_attached",
                        "nmt": {
                            "Identity & Context Attached": identity_context
                        }
                    }
                )
                context_span.set_attribute("tenant.name", "Ministry of Education")
                context_span.set_attribute("tenant.budget", "₹50,000")
                context_span.set_attribute("tenant.daily_quota", "10,000")
                context_span.set_attribute("tenant.data_tier", "Sensitive")
                context_span.set_attribute("contract.channel", "Web Portal")
                context_span.set_attribute("contract.use_case", "Policy Translation")
                context_span.set_attribute("contract.sensitivity", "High")
                context_span.set_attribute("contract.sla", "< 5s")
                context_span.set_attribute("runtime.language", identity_context["Runtime Analysis"]["Language"])
                
                # Collapsed: Policy check is now just attributes/events
                policy_check = {
                    "Budget Remaining": "₹43,215",
                    "Daily Quota Used": "2,847 / 10,000",
                    "Data Residency": "India Only",
                    "Language": f"{request.config.language.sourceLanguage} → {request.config.language.targetLanguage}",
                    "Status": "OK"
                }
                
                logger.info(
                    "Policy Check",
                    extra={
                        "event_type": "policy_check",
                        "nmt": {
                            "Policy Check": policy_check
                        }
                    }
                )
                context_span.set_attribute("policy.budget_remaining", "₹43,215")
                context_span.set_attribute("policy.daily_quota_used", "2,847 / 10,000")
                context_span.set_attribute("policy.data_residency", "India Only")
                context_span.set_attribute("policy.language", policy_check["Language"])
                context_span.set_attribute("policy.status", "OK")
                context_span.set_status(Status(StatusCode.OK))
            
            # Business-level span: Routing Decision
            with tracer.start_as_current_span("Routing Decision") as routing_span:
                routing_span.set_attribute("purpose", "Determines which translation model/provider to use based on quality, latency, and cost requirements")
                routing_span.set_attribute("user_visible", False)
                routing_span.set_attribute("impact_if_slow", "Minimal - this step is usually very fast")
                routing_span.set_attribute("owner", "Platform Team")
                
                smart_routing = {
                    "Primary Provider": "BharatNMT",
                    "Fallback Provider": "Indic-Trans",
                    "Auto Switch": "Enabled",
                    "Quality Target": "≥ 94%",
                    "Latency Target": "< 3s",
                    "Estimated Cost": "₹145"
                }
                
                logger.info(
                    "Smart Routing Decision",
                    extra={
                        "event_type": "smart_routing_decision",
                        "nmt": {
                            "Smart Routing Decision": smart_routing
                        }
                    }
                )
                routing_span.set_attribute("routing.primary_provider", "BharatNMT")
                routing_span.set_attribute("routing.fallback_provider", "Indic-Trans")
                routing_span.set_attribute("routing.auto_switch", "Enabled")
                routing_span.set_attribute("routing.quality_target", "≥ 94%")
                routing_span.set_attribute("routing.latency_target", "< 3s")
                routing_span.set_attribute("routing.estimated_cost", "₹145")
                routing_span.set_status(Status(StatusCode.OK))
            
            # Extract auth headers from incoming request to forward to model management service
            auth_headers = extract_auth_headers(http_request)
            
            # Log incoming request
            logger.info(f"Processing NMT inference request with {len(request.input)} texts")
            
            # Run inference
            response = await nmt_service.run_inference(
                request=request,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                auth_headers=auth_headers
            )
            
            # Business-level span: Response Construction
            with tracer.start_as_current_span("Response Construction") as response_span:
                response_span.set_attribute("purpose", "Formats the translation results into the final response structure")
                response_span.set_attribute("user_visible", False)
                response_span.set_attribute("impact_if_slow", "Minimal - this step is usually very fast")
                response_span.set_attribute("owner", "Language AI Platform")
                response_span.set_attribute("nmt.successful_outputs", len(response.output))
                response_span.set_attribute("nmt.output_count", len(response.output))
                
                # Track response size (approximate)
                try:
                    import json
                    response_size = len(json.dumps(response.dict()).encode('utf-8'))
                    response_span.set_attribute("http.response.size_bytes", response_size)
                except Exception:
                    pass
                
                response_span.set_status(Status(StatusCode.OK))
            
            # Add response metadata to main span
            span.set_attribute("nmt.output_count", len(response.output))
            span.set_attribute("nmt.successful_outputs", len(response.output))
            span.set_attribute("http.status_code", 200)
            span.set_status(Status(StatusCode.OK))
            
            logger.info(f"NMT inference completed successfully")
            return response
            
        except (InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError) as e:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            span.set_attribute("http.status_code", 400)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            logger.warning(f"Validation error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            
            # Extract context from request state for better error messages
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            # Return appropriate error based on exception type
            from services.nmt_service import TritonInferenceError
            if "Triton" in str(e) or "triton" in str(e).lower() or isinstance(e, TritonInferenceError):
                span.set_attribute("http.status_code", 503)
                error_detail = f"Triton inference failed for serviceId '{service_id}'"
                if triton_endpoint and model_name:
                    error_detail += f" at endpoint '{triton_endpoint}' with model '{model_name}': {str(e)}. "
                    error_detail += "Please verify the model is registered in Model Management and the Triton server is accessible."
                elif service_id:
                    error_detail += f": {str(e)}. Please verify the service is registered in Model Management."
                else:
                    error_detail += f": {str(e)}"
                span.set_status(Status(StatusCode.ERROR, error_detail))
                span.record_exception(e)
                logger.error(f"NMT inference failed: {e}", exc_info=True)
                raise HTTPException(status_code=503, detail=error_detail)
            else:
                span.set_attribute("http.status_code", 500)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"NMT inference failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"NMT inference failed: {str(e)}")


async def _run_inference_impl(
    request: NMTInferenceRequest,
    http_request: Request,
    nmt_service: NMTService,
) -> NMTInferenceResponse:
    """Fallback implementation when tracing is not available."""
    try:
        # Validate request
        validate_service_id(request.config.serviceId)
        validate_language_pair(
            request.config.language.sourceLanguage,
            request.config.language.targetLanguage
        )
        validate_batch_size(len(request.input))
        
        # Extract auth context from request.state
        user_id = getattr(http_request.state, 'user_id', None)
        api_key_id = getattr(http_request.state, 'api_key_id', None)
        session_id = getattr(http_request.state, 'session_id', None)
        
        # ============================================================
        # Simulated Future Functionality Logging
        # These logs simulate features that will be implemented
        # ============================================================
        
        # 1. Identity & Context Attached
        identity_context = {
            "Identity Details": {
                "Tenant": "Ministry of Education",
                "Budget": "₹50,000",
                "Daily Quota": "10,000",
                "Data Tier": "Sensitive"
            },
            "Contract Loaded": {
                "Channel": "Web Portal",
                "Use Case": "Policy Translation",
                "Sensitivity": "High",
                "Languages": ["Hindi", "English"],
                "SLA": "< 5s"
            },
            "Runtime Analysis": {
                "Language": f"{request.config.language.sourceLanguage} → {request.config.language.targetLanguage}"
            }
        }
        
        logger.info(
            "Identity & Context Attached",
            extra={
                "event_type": "identity_context_attached",
                "nmt": {
                    "Identity & Context Attached": identity_context
                }
            }
        )
        
        # 2. Policy Check
        policy_check = {
            "Budget Remaining": "₹43,215",
            "Daily Quota Used": "2,847 / 10,000",
            "Data Residency": "India Only",
            "Language": f"{request.config.language.sourceLanguage} → {request.config.language.targetLanguage}",
            "Status": "OK"
        }
        
        logger.info(
            "Policy Check",
            extra={
                "event_type": "policy_check",
                "nmt": {
                    "Policy Check": policy_check
                }
            }
        )
        
        # 3. Smart Routing Decision
        smart_routing = {
            "Primary Provider": "BharatNMT",
            "Fallback Provider": "Indic-Trans",
            "Auto Switch": "Enabled",
            "Quality Target": "≥ 94%",
            "Latency Target": "< 3s",
            "Estimated Cost": "₹145"
        }
        
        logger.info(
            "Smart Routing Decision",
            extra={
                "event_type": "smart_routing_decision",
                "nmt": {
                    "Smart Routing Decision": smart_routing
                }
            }
        )
        
        # Extract auth headers from incoming request to forward to model management service
        auth_headers = extract_auth_headers(http_request)
        
        # Log incoming request
        logger.info(f"Processing NMT inference request with {len(request.input)} texts")
        
        # Run inference
        response = await nmt_service.run_inference(
            request=request,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            auth_headers=auth_headers
        )
        
        logger.info(f"NMT inference completed successfully")
        return response
        
    except (InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError) as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"NMT inference failed: {e}", exc_info=True)
        
        # Extract context from request state for better error messages
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        model_name = getattr(http_request.state, "triton_model_name", None)
        
        # Return appropriate error based on exception type
        from services.nmt_service import TritonInferenceError
        if "Triton" in str(e) or "triton" in str(e).lower() or isinstance(e, TritonInferenceError):
            error_detail = f"Triton inference failed for serviceId '{service_id}'"
            if triton_endpoint and model_name:
                error_detail += f" at endpoint '{triton_endpoint}' with model '{model_name}': {str(e)}. "
                error_detail += "Please verify the model is registered in Model Management and the Triton server is accessible."
            elif service_id:
                error_detail += f": {str(e)}. Please verify the service is registered in Model Management."
            else:
                error_detail += f": {str(e)}"
            raise HTTPException(status_code=503, detail=error_detail)
        else:
            raise HTTPException(status_code=500, detail=f"NMT inference failed: {str(e)}")
