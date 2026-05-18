"""NMT (Neural Machine Translation) TaskService implementation."""

import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel
import httpx

from interfaces.task_service import BaseTaskService
from models.schemas.nmt import (
    NMTInferenceRequest,
    NMTInferenceResponse,
    NMTConfig,
)
from inference.inference_server_resolver import InferenceServerResolver

logger = logging.getLogger(__name__)

# Lazy import to avoid circular imports
_NMTInferenceModel = None

def get_nmt_inference_model():
    """Lazy load NMTInferenceModel."""
    global _NMTInferenceModel
    if _NMTInferenceModel is None:
        try:
            from inference_models.nmt_inference_model import NMTInferenceModel
            _NMTInferenceModel = NMTInferenceModel
        except ImportError:
            # For testing, create a stub
            class NMTInferenceModel:
                def convert_payload_to_triton_format(self, request):
                    return {}, []
                def convert_triton_output_to_task_format(self, output):
                    return {'output': []}
            _NMTInferenceModel = NMTInferenceModel
    return _NMTInferenceModel


class NMTTaskService(BaseTaskService):
    """
    TaskService for Neural Machine Translation inference.
    Handles translation requests between language pairs.
    """

    def __init__(
        self,
        inference_server_resolver: InferenceServerResolver,
        **dependencies: Any
    ):
        """
        Initialize NMT task service.

        Args:
            inference_server_resolver: Resolver for Triton endpoints
            **dependencies: Additional injected dependencies
        """
        super().__init__()
        self.inference_server_resolver = inference_server_resolver
        self.triton_client = None  # Initialized on first use
        self.logger = logger

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> NMTInferenceRequest:
        """
        Deserialize raw payload dictionary to NMTInferenceRequest.

        Args:
            payload: Raw request payload dictionary

        Returns:
            NMTInferenceRequest model instance

        Raises:
            ValueError: If deserialization fails
        """
        try:
            from models.schemas.nmt import TextInput, NMTConfig
            
            # Extract input items
            input_items = payload.get("input", [])
            if isinstance(input_items, list) and input_items:
                if isinstance(input_items[0], dict):
                    input_items = [TextInput(**item) for item in input_items]
            
            # Extract and deserialize config
            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = NMTConfig(**config_data)
            
            return NMTInferenceRequest(
                input=input_items,
                config=config_data
            )
        except Exception as e:
            raise ValueError(f"NMT: Failed to deserialize payload: {str(e)}")

    async def validate_request(self, request: BaseModel) -> None:
        """
        Validate NMT inference request.
        Checks input size constraints, language pair validity, etc.

        Args:
            request: NMT request to validate

        Raises:
            ValueError: If request is invalid
        """
        # Call base validation
        await super().validate_request(request)

        # Cast to typed request
        nmt_request = cast(NMTInferenceRequest, request)

        # Validate input data exists
        if not nmt_request.input:
            raise ValueError("NMT: input array cannot be empty")

        # Validate each input has source text
        for idx, item in enumerate(nmt_request.input):
            if not item.source or not isinstance(item.source, str):
                raise ValueError(f"NMT: input[{idx}]['source'] must be non-empty string")

        # Validate config
        config: NMTConfig = nmt_request.config
        if not config.language.source_language or not config.language.target_language:
            raise ValueError("NMT: sourceLanguage and targetLanguage are required")

        # Validate source and target are different
        if config.language.source_language == config.language.target_language:
            raise ValueError("NMT: sourceLanguage and targetLanguage cannot be the same")

        self.logger.info(
            f"NMT request validated: {config.language.source_language} -> "
            f"{config.language.target_language} ({len(nmt_request.input)} inputs)"
        )

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        """
        Preprocess input texts for NMT.
        Handles text normalization, removing extra whitespace, etc.

        Args:
            input_data: List of TextInput objects or text inputs with 'source' key

        Returns:
            Preprocessed input data
        """
        # Convert TextInput objects to dicts if needed
        input_list = []
        for item in input_data:
            if isinstance(item, dict):
                input_list.append(item)
            elif hasattr(item, 'dict'):
                # Pydantic model
                input_list.append(item.dict())
            elif hasattr(item, '__dict__'):
                # Plain object
                input_list.append(item.__dict__)
            else:
                input_list.append(item)
        
        # Call base preprocessing
        preprocessed = await super().preprocess_input(input_list)

        # Normalize and clean text
        cleaned = []
        for item in preprocessed:
            source_text = item.get('source', '')
            
            # Normalize whitespace
            normalized = ' '.join(source_text.split())
            
            # Remove leading/trailing whitespace
            normalized = normalized.strip()
            
            cleaned.append({
                'source': normalized,
                **{k: v for k, v in item.items() if k != 'source'}  # Keep other keys
            })

        self.logger.debug(f"NMT preprocessed {len(cleaned)} inputs")
        return cleaned

    async def run_inference(
        self,
        request: BaseModel,
    ) -> BaseModel:
        """
        Execute end-to-end NMT inference pipeline.
        Resolves service -> calls Triton -> postprocesses -> returns response.

        Args:
            request: NMT inference request

        Returns:
            NMT inference response with translations
        """
        # Cast to typed request
        nmt_request = cast(NMTInferenceRequest, request)
        config: NMTConfig = nmt_request.config

        try:
            # 1. Resolve service and model
            self.logger.info(
                f"Resolving NMT service for {config.language.source_language} -> "
                f"{config.language.target_language}"
            )
            service_id, model_name, triton_endpoint, api_key = await self._resolve_service_and_model(
                config
            )

            # 2. Convert payload to Triton format
            self.logger.debug(f"Converting payload to Triton format for model {model_name}")
            NMTInferenceModel = get_nmt_inference_model()
            inference_model = NMTInferenceModel()
            triton_inputs, output_names = inference_model.convert_payload_to_triton_format(
                nmt_request
            )

            # 3. Call Triton inference server
            self.logger.info(f"Calling Triton inference server: {triton_endpoint}")
            raw_triton_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                model_name=model_name,
                triton_inputs=triton_inputs,
                triton_outputs=output_names,
                api_key=api_key,
            )

            # 4. Convert Triton output to task format
            self.logger.debug("Converting Triton output to NMT response format")
            response_data = inference_model.convert_triton_output_to_task_format(raw_triton_output)

            # 5. Post-process output
            postprocessed = await self.postprocess_output(response_data)

            # 6. Create and return response
            response = NMTInferenceResponse(
                output=postprocessed['output'],
                smr_response=None,
            )

            self.logger.info(
                f"NMT inference completed successfully: service_id={service_id}, "
                f"outputs={len(response.output)}"
            )
            return response

        except Exception as e:
            self.logger.error(f"NMT inference failed: {str(e)}", exc_info=True)
            
            # Try fallback service if primary failed
            fallback_service = await self._handle_fallback_service(
                config.service_id, config
            )
            if fallback_service:
                self.logger.info("Attempting fallback NMT service")
                # Retry with fallback (same logic, different service)
                fallback_id, model_name, triton_endpoint, api_key = fallback_service
                NMTInferenceModel = get_nmt_inference_model()
                inference_model = NMTInferenceModel()
                triton_inputs, output_names = inference_model.convert_payload_to_triton_format(
                    nmt_request
                )
                raw_triton_output = await self._call_triton_inference(
                    triton_endpoint, model_name, triton_inputs, output_names, api_key
                )
                response_data = inference_model.convert_triton_output_to_task_format(
                    raw_triton_output
                )
                postprocessed = await self.postprocess_output(response_data)
                return NMTInferenceResponse(output=postprocessed['output'], smr_response=None)

            # If no fallback, re-raise error
            raise

    async def postprocess_output(
        self, raw_triton_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Post-process raw Triton output for NMT.
        Decodes translations, formats output, etc.

        Args:
            raw_triton_output: Raw output from Triton server

        Returns:
            Formatted output dictionary
        """
        # Call base post-processing
        postprocessed = await super().postprocess_output(raw_triton_output)

        # Extract translations from Triton output
        translations = []
        if 'translations' in postprocessed:
            translations = postprocessed['translations']
        elif 'output' in postprocessed:
            translations = postprocessed['output']

        # Ensure translations are strings
        output_list = []
        for translation in translations:
            if isinstance(translation, bytes):
                output_list.append(translation.decode('utf-8'))
            elif isinstance(translation, str):
                output_list.append(translation)
            else:
                output_list.append(str(translation))

        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {'output': output_list}

    async def _resolve_service_and_model(
        self, config: NMTConfig
    ) -> Tuple[str, str, str, Optional[str]]:
        """
        Resolve inference service and model information.
        Uses provided service_id or queries SMR for routing.

        Args:
            config: NMT config with optional service_id

        Returns:
            Tuple of (service_id, model_name, triton_endpoint, triton_api_key)

        Raises:
            RuntimeError: If service resolution fails
        """
        service_id = config.service_id

        # If service_id not provided, could use SMR (Smart Model Router)
        # For now, default to configured service
        if not service_id:
            service_id = "indictrans-v2-all"  # Default fallback
            self.logger.warning(f"No service_id provided, using default: {service_id}")

        # Resolve service using InferenceServerResolver
        self.logger.debug(f"Resolving service: {service_id}")
        try:
            service_info = await self.inference_server_resolver.resolve_service(service_id)
        except Exception as e:
            self.logger.error(f"Failed to resolve service {service_id}: {str(e)}")
            raise RuntimeError(f"NMT: Failed to resolve service {service_id}") from e

        # Extract fields from dict response
        model_name = service_info.get('model_name', '')
        triton_endpoint = service_info.get('triton_endpoint', '')
        api_key = service_info.get('api_key')

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                f"NMT: Invalid service info from resolver: missing model_name or triton_endpoint"
            )

        return (service_id, model_name, triton_endpoint, api_key)

    async def _call_triton_inference(
        self,
        triton_endpoint: str,
        model_name: str,
        triton_inputs: Dict[str, Any],
        triton_outputs: List[str],
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Triton inference server with prepared inputs.
        Uses HTTP protocol to query Triton.

        Args:
            triton_endpoint: Triton server URL (e.g., http://triton:8000)
            model_name: Model name in Triton
            triton_inputs: Formatted inputs for Triton (tensor format)
            triton_outputs: Expected output names
            api_key: Optional Triton API key for auth

        Returns:
            Raw output from Triton

        Raises:
            RuntimeError: If Triton call fails
        """
        try:
            # Build Triton HTTP request
            infer_url = f"{triton_endpoint}/v2/models/{model_name}/infer"

            # Prepare request payload
            payload = {
                "inputs": triton_inputs,
                "outputs": [{"name": name} for name in triton_outputs],
            }

            # Add auth header if provided
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # Make HTTP request to Triton
            async with httpx.AsyncClient() as client:
                self.logger.debug(f"Calling Triton: POST {infer_url}")
                response = await client.post(infer_url, json=payload, headers=headers, timeout=300.0)

            if response.status_code != 200:
                self.logger.error(
                    f"Triton returned status {response.status_code}: {response.text}"
                )
                raise RuntimeError(
                    f"Triton inference failed with status {response.status_code}"
                )

            # Parse response
            triton_response = response.json()
            self.logger.debug(f"Triton response received with {len(triton_response.get('outputs', []))} outputs")

            return triton_response

        except httpx.RequestError as e:
            self.logger.error(f"Failed to connect to Triton: {str(e)}")
            raise RuntimeError(f"NMT: Failed to connect to Triton server") from e

    async def _handle_fallback_service(
        self,
        primary_service_id: Optional[str],
        config: NMTConfig,
    ) -> Optional[Tuple[str, str, str, Optional[str]]]:
        """
        Handle fallback to alternate service on primary failure.
        Returns None if no fallback available.

        Args:
            primary_service_id: Primary service ID that failed
            config: NMT config

        Returns:
            Fallback service info tuple or None if no fallback
        """
        # Define fallback services for NMT
        fallback_services: Dict[str, List[str]] = {
            "indictrans-v2-all": ["indictrans-v1", "nllb-200"],
        }

        if not primary_service_id:
            self.logger.info("No primary service_id to fallback from")
            return None

        fallback_list = fallback_services.get(primary_service_id, [])
        if not fallback_list:
            self.logger.info(f"No fallback available for {primary_service_id}")
            return None

        # Try first fallback
        fallback_service_id = fallback_list[0]
        self.logger.info(f"Using fallback service: {fallback_service_id}")

        try:
            service_info = await self.inference_server_resolver.resolve_service(fallback_service_id)
            # Extract fields from dict response
            model_name = service_info.get('model_name', '')
            triton_endpoint = service_info.get('triton_endpoint', '')
            api_key = service_info.get('api_key')

            return (fallback_service_id, model_name, triton_endpoint, api_key)
        except Exception as e:
            self.logger.error(f"Fallback service resolution failed: {str(e)}")
            return None
