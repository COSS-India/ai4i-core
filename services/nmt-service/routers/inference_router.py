"""
Inference Router
FastAPI router for NMT inference endpoints
"""

import logging
import time
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from models.nmt_request import NMTInferenceRequest
from models.nmt_response import NMTInferenceResponse
from repositories.nmt_repository import NMTRepository
from services.nmt_service import NMTService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.model_management_client import ModelManagementClient
from utils.validation_utils import (
    validate_language_pair, validate_service_id, validate_batch_size,
    InvalidLanguagePairError, InvalidServiceIdError, BatchSizeExceededError
)
from middleware.auth_provider import AuthProvider
from middleware.exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

# Create router
inference_router = APIRouter(
    prefix="/api/v1/nmt",
    tags=["NMT Inference"],
    # dependencies=[Depends(AuthProvider)]  # Commented out for testing
)


def extract_auth_headers(request: Request) -> Dict[str, str]:
    """Extract authentication headers from incoming request to forward to model management service"""
    auth_headers = {}
    
    # FastAPI headers are case-insensitive, but we need to check both ways
    # Check Authorization header (case-insensitive)
    authorization = request.headers.get("Authorization") or request.headers.get("authorization")
    if authorization:
        auth_headers["Authorization"] = authorization
        logger.debug(f"Extracted Authorization header: {authorization[:20]}...")
    
    # Check X-API-Key header (case-insensitive)
    x_api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if x_api_key:
        auth_headers["X-API-Key"] = x_api_key
        logger.debug(f"Extracted X-API-Key header: {x_api_key[:20]}...")
    
    # Check X-Auth-Source header (important for JWT vs API key authentication)
    x_auth_source = request.headers.get("X-Auth-Source") or request.headers.get("x-auth-source")
    if x_auth_source:
        auth_headers["X-Auth-Source"] = x_auth_source
        logger.debug(f"Extracted X-Auth-Source header: {x_auth_source}")
    
    # Also check all headers for case-insensitive variants
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower == "authorization" and "Authorization" not in auth_headers:
            auth_headers["Authorization"] = value
            logger.debug(f"Found Authorization header via iteration: {value[:20]}...")
        elif key_lower == "x-api-key" and "X-API-Key" not in auth_headers:
            auth_headers["X-API-Key"] = value
            logger.debug(f"Found X-API-Key header via iteration: {value[:20]}...")
        elif key_lower == "x-auth-source" and "X-Auth-Source" not in auth_headers:
            auth_headers["X-Auth-Source"] = value
            logger.debug(f"Found X-Auth-Source header via iteration: {value}")
    
    if not auth_headers:
        logger.warning("No auth headers found in request. Available headers: %s", list(request.headers.keys()))
    
    return auth_headers


async def get_db_session(request: Request) -> AsyncSession:
    """Dependency to get database session"""
    return request.app.state.db_session_factory()


def create_triton_client(triton_url: str, api_key: str) -> TritonClient:
    """Factory function to create Triton client"""
    return TritonClient(triton_url=triton_url, api_key=api_key)


async def get_nmt_service(request: Request, db: AsyncSession = Depends(get_db_session)) -> NMTService:
    """Dependency to get configured NMT service"""
    repository = NMTRepository(db)
    text_service = TextService()
    
    # Default Triton client
    default_triton_client = TritonClient(
        triton_url=request.app.state.triton_endpoint,
        api_key=request.app.state.triton_api_key
    )
    
    # Factory function to create Triton clients for different endpoints
    def get_triton_client_for_endpoint(endpoint: str) -> TritonClient:
        """Create Triton client for specific endpoint"""
        # Use default API key for now (can be extended to support per-endpoint keys)
        return TritonClient(
            triton_url=endpoint,
            api_key=request.app.state.triton_api_key
        )
    
    # Get model management client from app state
    model_management_client = getattr(request.app.state, "model_management_client", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    
    return NMTService(
        repository, 
        text_service, 
        default_triton_client,
        get_triton_client_for_endpoint,
        model_management_client=model_management_client,
        redis_client=redis_client
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
        # Return more detailed error in development, generic in production
        import traceback
        error_detail = {
            "message": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc() if logger.level <= logging.DEBUG else None
        }
        raise HTTPException(status_code=500, detail=error_detail)


@inference_router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available NMT models",
    description="Get list of supported NMT models and language pairs"
)
async def list_models(request: Request) -> Dict[str, Any]:
    """List available NMT models and language pairs from model management service"""
    model_management_client = getattr(request.app.state, "model_management_client", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    
    if not model_management_client:
        logger.warning("Model management client not available, returning empty list")
        return {"models": [], "total_models": 0}
    
    # Extract auth headers from incoming request
    auth_headers = extract_auth_headers(request)
    
    try:
        # Get all NMT services and extract unique models from them
        services = await model_management_client.list_services(
            use_cache=True,
            redis_client=redis_client,
            auth_headers=auth_headers,
            task_type="nmt"  # Filter for NMT services only
        )
        
        # Build a map of unique models from services
        # For each unique model, we'll fetch one service to get full model details
        models_map = {}
        services_by_model = {}  # Track which service to use for each model
        
        # First pass: collect unique models and pick a representative service for each
        for service in services:
            model_id = service.model_id
            if model_id not in models_map:
                models_map[model_id] = {
                    "model_id": model_id,
                    "name": None,  # Will be filled from service details
                    "description": None,
                    "supported_languages": [],
                    "max_batch_size": 90,
                    "supported_scripts": [],
                    "domain": []
                }
                services_by_model[model_id] = service.service_id
        
        # Second pass: fetch service details for each unique model to get full model info
        # We'll fetch in parallel for efficiency
        import asyncio
        service_details_tasks = []
        for model_id, service_id in services_by_model.items():
            service_details_tasks.append(
                model_management_client.get_service(service_id, use_cache=True, redis_client=redis_client, auth_headers=auth_headers)
            )
        
        service_details_list = await asyncio.gather(*service_details_tasks, return_exceptions=True)
        
        # Update models_map with full details from service responses
        for idx, (model_id, service_detail) in enumerate(zip(services_by_model.keys(), service_details_list)):
            if isinstance(service_detail, Exception):
                logger.warning(f"Failed to fetch service details for model {model_id}: {service_detail}")
                continue
            
            if not service_detail:
                continue
            
            # Extract languages
            languages = []
            if service_detail.languages:
                for lang in service_detail.languages:
                    if isinstance(lang, dict):
                        lang_code = lang.get("sourceLanguage") or lang.get("targetLanguage") or lang.get("code")
                        if lang_code:
                            languages.append(lang_code)
                    elif isinstance(lang, str):
                        languages.append(lang)
            
            # Extract scripts from task
            scripts = []
            if service_detail.model_task and isinstance(service_detail.model_task, dict):
                scripts_data = service_detail.model_task.get("supportedScripts") or service_detail.model_task.get("scripts", [])
                if isinstance(scripts_data, list):
                    scripts = scripts_data
            
            # Update model info
            models_map[model_id].update({
                "name": service_detail.model_name or model_id,
                "description": service_detail.model_description or "",
                "supported_languages": languages,
                "supported_scripts": scripts if scripts else [],
                "domain": service_detail.model_domain or []
            })
        
        model_list = list(models_map.values())
        
        return {
            "models": model_list,
            "total_models": len(model_list)
        }
    except Exception as e:
        logger.error(f"Error fetching models from model management service: {e}", exc_info=True)
        # Return empty list on error rather than failing completely
        return {"models": [], "total_models": 0, "error": "Failed to fetch models from model management service"}


@inference_router.get(
    "/services",
    response_model=Dict[str, Any],
    summary="List available NMT services",
    description="Get list of supported NMT services with their Triton endpoints"
)
async def list_services(request: Request) -> Dict[str, Any]:
    """List available NMT services and their endpoints from model management service"""
    model_management_client = getattr(request.app.state, "model_management_client", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    
    if not model_management_client:
        logger.warning("Model management client not available, returning empty list")
        return {"services": [], "total_services": 0}
    
    # Extract auth headers from incoming request
    auth_headers = extract_auth_headers(request)
    logger.info(f"Extracted auth headers for list_services: {list(auth_headers.keys())}")
    logger.info(f"All request headers: {list(request.headers.keys())}")
    
    if not auth_headers:
        logger.warning("No auth headers extracted from request. This may cause 401 errors.")
        logger.warning(f"Request headers available: {dict(request.headers)}")
    
    try:
        services = await model_management_client.list_services(
            use_cache=True,
            redis_client=redis_client,
            auth_headers=auth_headers,
            task_type="nmt"  # Filter for NMT services only
        )
        
        # Transform to response format
        service_list = []
        for service in services:
            # Extract languages from service data
            languages = []
            if service.languages:
                for lang in service.languages:
                    if isinstance(lang, dict):
                        lang_code = lang.get("sourceLanguage") or lang.get("targetLanguage") or lang.get("code")
                        if lang_code:
                            languages.append(lang_code)
                    elif isinstance(lang, str):
                        languages.append(lang)
            
            # Extract endpoint (remove http:// if present)
            endpoint = service.endpoint
            if endpoint:
                endpoint = endpoint.replace("http://", "").replace("https://", "")
            
            service_dict = {
                "service_id": service.service_id,
                "model_id": service.model_id,
                "triton_endpoint": endpoint,
                "triton_model": service.triton_model or "nmt",
                "name": service.name or service.service_id,
                "description": service.description or "",
                "supported_languages": languages
            }
            service_list.append(service_dict)
        
        return {
            "services": service_list,
            "total_services": len(service_list)
        }
    except Exception as e:
        logger.error(f"Error fetching services from model management service: {e}", exc_info=True)
        # Return empty list on error rather than failing completely
        return {"services": [], "total_services": 0, "error": "Failed to fetch services from model management service"}


@inference_router.get(
    "/languages",
    response_model=Dict[str, Any],
    summary="Get supported languages",
    description="Get list of supported languages for a specific NMT model or service"
)
async def list_languages(
    request: Request,
    model_id: Optional[str] = Query(None, description="Model ID to get languages for"),
    service_id: Optional[str] = Query(None, description="Service ID to get languages for")
) -> Dict[str, Any]:
    """List supported languages for a specific NMT model or service from model management service"""
    model_management_client = getattr(request.app.state, "model_management_client", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    
    if not model_management_client:
        logger.warning("Model management client not available")
        raise HTTPException(
            status_code=503,
            detail="Model management service is not available"
        )
    
    # Normalize input parameters
    if service_id:
        service_id = service_id.strip()
    if model_id:
        model_id = model_id.strip()
    
    # Log received parameters for debugging
    logger.info(f"list_languages called with service_id={service_id}, model_id={model_id}")
    
    # Extract auth headers from incoming request
    auth_headers = extract_auth_headers(request)
    
    try:
        # Determine service_id - if model_id is provided, we need to find a service for that model
        if model_id and not service_id:
            # Get all NMT services and find one that uses this model
            services = await model_management_client.list_services(
                use_cache=True,
                redis_client=redis_client,
                auth_headers=auth_headers,
                task_type="nmt"  # Filter for NMT services only
            )
            matching_service = None
            for svc in services:
                if svc.model_id == model_id:
                    matching_service = svc
                    break
            
            if not matching_service:
                raise HTTPException(
                    status_code=404,
                    detail=f"No service found for model '{model_id}'"
                )
            service_id = matching_service.service_id
            logger.info(f"Mapped model_id '{model_id}' to service_id '{service_id}'")
        
        if not service_id:
            raise HTTPException(
                status_code=400,
                detail="Either model_id or service_id must be provided"
            )
        
        # Normalize service_id
        service_id = service_id.strip()
        logger.info(f"Final service_id for lookup: '{service_id}'")
        
        # Fetch service details (which includes model information)
        service_info = await model_management_client.get_service(
            service_id,
            use_cache=True,
            redis_client=redis_client,
            auth_headers=auth_headers
        )
        
        if not service_info:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found"
            )
        
        # Extract languages from service (which includes model data)
        languages = []
        language_details = []
        
        if service_info.languages:
            for lang in service_info.languages:
                if isinstance(lang, dict):
                    lang_code = lang.get("sourceLanguage") or lang.get("targetLanguage") or lang.get("code")
                    lang_name = lang.get("name") or lang.get("languageName") or lang_code
                    if lang_code:
                        languages.append(lang_code)
                        language_details.append({"code": lang_code, "name": lang_name})
                elif isinstance(lang, str):
                    languages.append(lang)
                    language_details.append({"code": lang, "name": lang})
        
        # Extract scripts from task if available
        scripts = []
        if service_info.model_task and isinstance(service_info.model_task, dict):
            scripts_data = service_info.model_task.get("supportedScripts") or service_info.model_task.get("scripts", [])
            if isinstance(scripts_data, list):
                scripts = scripts_data
        
        # Extract provider from task if available
        provider = "Unknown"
        if service_info.model_task and isinstance(service_info.model_task, dict):
            provider = service_info.model_task.get("provider") or service_info.model_task.get("submitter", {}).get("name", "Unknown")
        
        return {
            "model_id": service_info.model_id,
            "name": service_info.model_name or service_info.model_id,
            "provider": provider,
            "supported_languages": languages,
            "language_details": language_details,
            "total_languages": len(languages),
            "supported_scripts": scripts if scripts else []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching language information: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching language information: {str(e)}"
        )
