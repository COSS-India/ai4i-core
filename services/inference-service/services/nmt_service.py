"""NMT (Neural Machine Translation) TaskService implementation."""

import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel

from interfaces.task_service import BaseTaskService
from models.schemas.nmt import (
    NMTInferenceRequest,
    NMTInferenceResponse,
    NMTConfig,
)
from inference.inference_server_resolver import InferenceServerResolver
from inference_models.nmt_inference_model import NMTInferenceModel  # type: ignore[import]
from utils.http_client import HTTPServiceClient

logger = logging.getLogger(__name__)


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

        # Extract source texts upfront for use in error handling
        source_texts = []
        for item in nmt_request.input:
            if isinstance(item, dict):
                source_texts.append(item.get('source', ''))
            elif hasattr(item, 'source'):
                source_texts.append(item.source)
            else:
                source_texts.append('')

        try:
            # 1. Resolve service and model
            self.logger.info(
                f"Resolving NMT service for {config.language.source_language} -> "
                f"{config.language.target_language}"
            )
            # adapter_config is the tensor mapping for the resolved model
            service_id, model_name, triton_endpoint, api_key, adapter_config = (
                await self._resolve_service_and_model(config)
            )

            # 2. Run inference pipeline: build model → format payload → call Triton → convert output
            self.logger.debug(f"Converting payload to Triton format for model {model_name}")
            self.logger.info(f"Calling Triton inference server: {triton_endpoint}")
            response_data = await self._run_triton_pipeline(
                adapter_config, triton_endpoint, api_key,
                nmt_request.input, nmt_request.config.dict()
            )

            # 5. Post-process output and pair with source inputs
            postprocessed = await self.postprocess_output(response_data, source_texts)

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
                # Same pattern as primary — fallback model also gets its own adapter_config
                fallback_id, model_name, triton_endpoint, api_key, fallback_adapter_config = (
                    fallback_service
                )
                response_data = await self._run_triton_pipeline(
                    fallback_adapter_config, triton_endpoint, api_key,
                    nmt_request.input, nmt_request.config.dict()
                )
                postprocessed = await self.postprocess_output(response_data, source_texts)
                return NMTInferenceResponse(output=postprocessed["output"], smr_response=None)

            # If no fallback, re-raise error
            raise

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Pair mapped output items with their source texts to build the final response.

        Args:
            response_items: List[Dict] from convert_triton_output_to_task_format().
                Each dict has keys matching 'maps_to' in adapter_config outputs
                (e.g. {"target": "translated text"}).
            source_texts: Original input texts in the same order, used to populate
                TranslationOutput.source.

        Returns:
            Dict with 'output' key containing List[TranslationOutput].
        """
        # Base class call is intentionally skipped here.
        # It only validates non-empty and returns input unchanged — not needed for typed output building.
        # postprocessed = await super().postprocess_output(response_items)

        # response_items is already the mapper output — each dict has 'target' key
        # because adapter_config declares maps_to: "target" for the OUTPUT_TEXT tensor.
        output_list = []
        for idx, item in enumerate(response_items):
            target_text = item.get("target", "")
            if isinstance(target_text, bytes):
                # Triton BYTES tensors can arrive as raw bytes — decode to string
                target_text = target_text.decode("utf-8")
            source_text = source_texts[idx] if source_texts and idx < len(source_texts) else ""
            from models.schemas.nmt import TranslationOutput
            output_list.append(TranslationOutput(source=source_text, target=target_text))

        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}

    async def _resolve_service_and_model(
        self, config: NMTConfig
    ) -> Tuple[str, str, str, Optional[str], Optional[Any]]:
        """
        Resolve the model service details for the given NMT config.

        Args:
            config: NMT config — service_id identifies which model to use.

        Returns:
            Tuple of (service_id, model_name, triton_endpoint, api_key, adapter_config).
            adapter_config holds the tensor I/O mapping for the specific model at this endpoint.
            Different service_ids can return different adapter_configs — no code change needed
            to support a new model, only a new service registration with its own adapter_config.

        Raises:
            RuntimeError: If service resolution fails.
        """
        service_id = config.service_id

        if not service_id:
            service_id = "indictrans-v2-all"
            self.logger.warning(f"No service_id provided, using default: {service_id}")

        self.logger.debug(f"Resolving service: {service_id}")
        try:
            service_info = await self.inference_server_resolver.resolve_service(service_id)
        except Exception as e:
            self.logger.error(
                f"Failed to resolve service {service_id}: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise RuntimeError(f"NMT: Failed to resolve service {service_id}: {str(e)}") from e

        model_name = service_info.get("name", "")
        triton_endpoint = service_info.get("endpoint", "")
        api_key = service_info.get("api_key")
        # adapter_config carries the tensor mapping (inputs/outputs) for this specific model
        adapter_config = service_info.get("adapter_config")

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                "NMT: Invalid service info from resolver: missing model_name or triton_endpoint"
            )

        return (service_id, model_name, triton_endpoint, api_key, adapter_config)

    async def _run_triton_pipeline(
        self,
        adapter_config: Any,
        triton_endpoint: str,
        api_key: Optional[str],
        input_data: List[Any],
        config_dict: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Build inference model, format payload, call Triton, convert output."""
        inference_model = NMTInferenceModel(adapter_config=adapter_config)
        triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
            input_data, config_dict
        )
        payload = {
            "inputs": triton_inputs,
            "outputs": [{"name": name} for name in triton_outputs],
        }
        raw_triton_output = await self._call_triton_inference(triton_endpoint, payload, api_key)
        return await inference_model.convert_triton_output_to_task_format(raw_triton_output)

    async def _call_triton_inference(
        self,
        url: str,
        payload: Dict[str, Any],
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST inference payload to Triton and return the raw response."""
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            return await HTTPServiceClient(timeout=300).post_json(url, payload, headers)
        except Exception as e:
            raise RuntimeError(f"Triton inference call failed at {url}: {str(e)}") from e

    async def _handle_fallback_service(
        self,
        primary_service_id: Optional[str],
        config: NMTConfig,
    ) -> Optional[Tuple[str, str, str, Optional[str], Optional[Any]]]:
        """
        Attempt to resolve a fallback service when the primary fails.

        Args:
            primary_service_id: The service_id that failed.
            config: NMT config.

        Returns:
            Tuple of (service_id, model_name, triton_endpoint, api_key, adapter_config),
            or None if no fallback is available.
        """
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

        fallback_service_id = fallback_list[0]
        self.logger.info(f"Using fallback service: {fallback_service_id}")

        try:
            service_info = await self.inference_server_resolver.resolve_service(fallback_service_id)
            # Use the same response keys as the primary path — 'name' and 'endpoint'
            model_name = service_info.get("name", "")
            triton_endpoint = service_info.get("endpoint", "")
            api_key = service_info.get("api_key")
            adapter_config = service_info.get("adapter_config")

            return (fallback_service_id, model_name, triton_endpoint, api_key, adapter_config)
        except Exception as e:
            self.logger.error(f"Fallback service resolution failed: {str(e)}")
            return None
