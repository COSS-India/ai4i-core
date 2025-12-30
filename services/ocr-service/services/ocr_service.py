"""
Core business logic for OCR inference.

This mirrors the behavior of Dhruva's /services/inference/ocr while fitting
into the microservice structure used by ASR/TTS/NMT in this repository.
"""

import base64
import logging
import time
from typing import List, Optional, Dict, Tuple

import requests

from models.ocr_request import OCRInferenceRequest, ImageInput
from models.ocr_response import OCRInferenceResponse, TextOutput
from utils.triton_client import TritonClient, TritonInferenceError
from ai4icore_model_management import ModelManagementClient, ServiceInfo

logger = logging.getLogger(__name__)


class OCRService:
    """
    OCR inference service.

    Responsibilities:
    - Take OCRInferenceRequest
    - For each image:
      - Resolve base64 content (direct or via imageUri download)
      - Call Triton (Surya OCR) using model management service
      - Map OCR model output to OCRInferenceResponse
    """

    def __init__(
        self,
        get_triton_client_func,
        model_management_client: ModelManagementClient,
        redis_client = None,
        cache_ttl_seconds: int = 300
    ):
        """
        Initialize OCRService
        
        Args:
            get_triton_client_func: Factory function to create Triton clients
            model_management_client: Client for model management service (REQUIRED)
            redis_client: Optional Redis client for distributed caching
            cache_ttl_seconds: Cache TTL in seconds
        """
        if model_management_client is None:
            raise ValueError("model_management_client is required. Model management service must be available.")
        
        self.get_triton_client_func = get_triton_client_func
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._triton_clients = {}  # Cache for Triton clients
        
        # Service info cache (service_id -> (ServiceInfo, expires_at))
        self._service_info_cache: Dict[str, Tuple[ServiceInfo, float]] = {}
        
        # Service registry cache (service_id -> (endpoint, model_name, expires_at))
        self._service_registry_cache: Dict[str, Tuple[str, str, float]] = {}

    async def _get_service_info(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> ServiceInfo:
        """
        Get service info from model management service with caching
        
        Args:
            service_id: Service ID to fetch
            auth_headers: Optional auth headers from incoming request
            
        Returns:
            ServiceInfo object
            
        Raises:
            ValueError: If service not found or model management service error
        """
        # Check cache first
        cached = self._service_info_cache.get(service_id)
        if cached:
            service_info, expires_at = cached
            if expires_at > time.time():
                logger.debug(f"Service info cache hit for {service_id}")
                return service_info
            # Expired entry
            self._service_info_cache.pop(service_id, None)
        
        # Fetch from model management service (REQUIRED)
        try:
            logger.info(f"Fetching service info for {service_id} from model management service")
            service_info = await self.model_management_client.get_service(
                service_id,
                use_cache=True,
                redis_client=self.redis_client,
                auth_headers=auth_headers
            )
            
            if service_info is None:
                error_msg = (
                    f"Service ID '{service_id}' not found in model management service. "
                    f"Please verify the service ID is correct and register the service in the model management service."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Validate service info has required fields
            if not service_info.endpoint:
                error_msg = (
                    f"Service ID '{service_id}' has no Triton endpoint configured in model management service. "
                    f"Please configure the endpoint for this service."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Cache the service info
            expires_at = time.time() + self.cache_ttl_seconds
            self._service_info_cache[service_id] = (service_info, expires_at)
            
            # Also update registry cache
            endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
            self._service_registry_cache[service_id] = (endpoint, model_name, expires_at)
            
            logger.info(f"Successfully fetched and cached service info for {service_id}")
            return service_info
            
        except ValueError:
            # Re-raise ValueError as-is (already has proper error message)
            raise
        except Exception as e:
            error_msg = (
                f"Failed to fetch service info for service ID '{service_id}' from model management service: {e}. "
                f"Please verify the model management service is available and the service ID is correct."
            )
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
    
    def _extract_triton_metadata(self, service_info: ServiceInfo, service_id: str) -> Tuple[str, str]:
        """
        Extract Triton endpoint and model name from ServiceInfo
        
        Args:
            service_info: ServiceInfo from model management service
            service_id: Service ID for logging
            
        Returns:
            Tuple of (endpoint, model_name)
        """
        # Extract endpoint (remove http:// or https:// prefix if present)
        endpoint = service_info.endpoint or ""
        endpoint = endpoint.replace("http://", "").replace("https://", "").strip()
        
        # Extract model name - try multiple sources
        model_name = service_info.triton_model or "surya_ocr"
        
        # Check model_inference_endpoint for model name
        if service_info.model_inference_endpoint:
            if isinstance(service_info.model_inference_endpoint, dict):
                endpoint_model_name = service_info.model_inference_endpoint.get("modelName")
                if endpoint_model_name:
                    model_name = endpoint_model_name
        
        logger.info(f"Extracted Triton metadata for {service_id}: endpoint={endpoint}, model_name={model_name}")
        return endpoint, model_name
    
    async def _get_service_registry_entry(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
        """
        Get service registry entry (endpoint, model_name) for the given service ID
        
        Tries in order:
        1. Service registry cache
        2. Model management service (REQUIRED)
        
        Args:
            service_id: Service ID to fetch
            auth_headers: Optional auth headers from incoming request
            
        Returns:
            Tuple of (endpoint, model_name)
            
        Raises:
            ValueError: If service not found or error fetching from model management
        """
        # Check registry cache first
        cached = self._service_registry_cache.get(service_id)
        if cached:
            endpoint, model_name, expires_at = cached
            if expires_at > time.time():
                logger.debug(f"Service registry cache hit for {service_id}")
                return (endpoint, model_name)
            # Expired entry
            self._service_registry_cache.pop(service_id, None)
        
        # Get from model management service (REQUIRED - will raise ValueError if not found)
        service_info = await self._get_service_info(service_id, auth_headers)
        endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
        return (endpoint, model_name)
    
    async def get_triton_client(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> TritonClient:
        """
        Get Triton client for the given service ID
        
        Args:
            service_id: Service ID to get client for
            auth_headers: Optional auth headers from incoming request
            
        Returns:
            TritonClient configured for the service endpoint
            
        Raises:
            ValueError: If service not found or endpoint not configured
        """
        # Check cache first
        if service_id in self._triton_clients:
            logger.debug(f"Triton client cache hit for {service_id}")
            return self._triton_clients[service_id]
        
        # Get endpoint and model info from model management service (REQUIRED)
        endpoint, _ = await self._get_service_registry_entry(service_id, auth_headers)
        
        # Create client using factory function
        logger.info(f"Creating Triton client for service {service_id} with endpoint {endpoint}")
        client = self.get_triton_client_func(endpoint)
        self._triton_clients[service_id] = client
        return client
    
    async def get_model_name(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> str:
        """
        Get Triton model name based on service ID
        
        Args:
            service_id: Service ID to get model name for
            auth_headers: Optional auth headers from incoming request
            
        Returns:
            Triton model name
            
        Raises:
            ValueError: If service not found
        """
        _, model_name = await self._get_service_registry_entry(service_id, auth_headers)
        return model_name

    def _resolve_image_base64(self, image: ImageInput) -> Optional[str]:
        """
        Resolve an image into base64:

        - If imageContent is provided, use it directly
        - Else, download from imageUri and base64-encode it
        """
        if image.imageContent:
            return image.imageContent

        if image.imageUri:
            try:
                resp = requests.get(str(image.imageUri), timeout=30)
                resp.raise_for_status()
                return base64.b64encode(resp.content).decode("utf-8")
            except Exception as exc:
                logger.error(
                    "Failed to download image from %s: %s", image.imageUri, exc
                )
                return None

        # No content and no URI
        return None

    async def run_inference(
        self,
        request: OCRInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> OCRInferenceResponse:
        """
        Async OCR inference entrypoint.
        
        Args:
            request: OCR inference request
            user_id: Optional user ID
            api_key_id: Optional API key ID
            session_id: Optional session ID
            auth_headers: Optional auth headers for model management service calls
            
        Returns:
            OCRInferenceResponse with OCR results
        """
        # Extract configuration
        service_id = request.config.serviceId
        
        # Get model name dynamically based on service ID (from model management service)
        model_name = await self.get_model_name(service_id, auth_headers)
        
        # Resolve all images to base64 first
        images_b64: List[str] = []
        for img in request.image:
            resolved = self._resolve_image_base64(img)
            if not resolved:
                images_b64.append("")
            else:
                images_b64.append(resolved)

        # Call Triton in a single batch for all non-empty images
        outputs: List[TextOutput] = []
        try:
            # For empty entries, we'll skip Triton and just return empty text
            non_empty_indices = [i for i, v in enumerate(images_b64) if v]
            non_empty_images = [images_b64[i] for i in non_empty_indices]

            ocr_results: List[dict] = []
            if non_empty_images:
                # Get appropriate Triton client for this service (from model management service)
                triton_client = await self.get_triton_client(service_id, auth_headers)
                
                # Log the model name and endpoint for debugging
                registry_entry = await self._get_service_registry_entry(service_id, auth_headers)
                endpoint = registry_entry[0] if registry_entry else "default"
                logger.info(f"Using Triton endpoint: {endpoint}, model: {model_name} for service: {service_id}")
                
                batch_results = triton_client.run_ocr_batch(non_empty_images, model_name)
                ocr_results = batch_results

            # Map back to original indices
            result_map = {idx: {} for idx in range(len(images_b64))}
            for local_idx, global_idx in enumerate(non_empty_indices):
                if local_idx < len(ocr_results):
                    result_map[global_idx] = ocr_results[local_idx] or {}
        except TritonInferenceError as exc:
            logger.error("OCR Triton inference failed: %s", exc)
            raise  # Re-raise to be handled by router
        except ValueError as exc:
            # Service ID or endpoint errors from model management
            logger.error("OCR service configuration error: %s", exc)
            raise  # Re-raise to be handled by router

        # Build TextOutput list
        for idx in range(len(request.image)):
            ocr_result = result_map.get(idx, {})  # type: ignore[name-defined]
            if not images_b64[idx] or not ocr_result or not ocr_result.get(
                "success", False
            ):
                outputs.append(TextOutput(source="", target=""))
                continue

            full_text = ocr_result.get("full_text", "") or ""
            outputs.append(TextOutput(source=full_text, target=""))

        return OCRInferenceResponse(output=outputs, config=request.config.dict())


