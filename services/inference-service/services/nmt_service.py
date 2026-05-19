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
        super().__init__()
        self.inference_server_resolver = inference_server_resolver
        self.triton_client = None  # Initialized on first use
        self.logger = logger

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> NMTInferenceRequest:
        try:
            from models.schemas.nmt import TextInput, NMTConfig

            input_items = payload.get("input", [])
            if isinstance(input_items, list) and input_items:
                if isinstance(input_items[0], dict):
                    input_items = [TextInput(**item) for item in input_items]

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
        await super().validate_request(request)

        nmt_request = cast(NMTInferenceRequest, request)

        if not nmt_request.input:
            raise ValueError("NMT: input array cannot be empty")

        for idx, item in enumerate(nmt_request.input):
            if not item.source or not isinstance(item.source, str):
                raise ValueError(f"NMT: input[{idx}]['source'] must be non-empty string")

        config: NMTConfig = nmt_request.config
        if not config.language.source_language or not config.language.target_language:
            raise ValueError("NMT: sourceLanguage and targetLanguage are required")

        if config.language.source_language == config.language.target_language:
            raise ValueError("NMT: sourceLanguage and targetLanguage cannot be the same")

        self.logger.info(
            f"NMT request validated: {config.language.source_language} -> "
            f"{config.language.target_language} ({len(nmt_request.input)} inputs)"
        )

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        input_list = []
        for item in input_data:
            if isinstance(item, dict):
                input_list.append(item)
            elif hasattr(item, 'dict'):
                input_list.append(item.dict())
            elif hasattr(item, '__dict__'):
                input_list.append(item.__dict__)
            else:
                input_list.append(item)

        preprocessed = await super().preprocess_input(input_list)

        cleaned = []
        for item in preprocessed:
            source_text = item.get('source', '')
            normalized = ' '.join(source_text.split())
            normalized = normalized.strip()
            cleaned.append({
                'source': normalized,
                **{k: v for k, v in item.items() if k != 'source'}
            })

        self.logger.debug(f"NMT preprocessed {len(cleaned)} inputs")
        return cleaned

    async def run_inference(
        self,
        request: BaseModel,
    ) -> BaseModel:
        nmt_request = cast(NMTInferenceRequest, request)
        config: NMTConfig = nmt_request.config

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
            service_id, model_name, triton_endpoint, api_key, adapter_config = (
                await self._resolve_service_and_model(config)
            )

            # 2. Convert payload to Triton format
            self.logger.debug(f"Converting payload to Triton format for model {model_name}")
            inference_model = NMTInferenceModel(adapter_config=adapter_config)
            triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
                nmt_request.input, nmt_request.config.dict()
            )

            # 3. Call Triton inference server
            self.logger.info(f"Calling Triton inference server: {triton_endpoint}")
            raw_triton_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                triton_inputs=triton_inputs,
                triton_outputs=triton_outputs,
                api_key=api_key,
            )

            # 4. Convert Triton output to task format
            self.logger.debug("Converting Triton output to NMT response format")
            response_data = await inference_model.convert_triton_output_to_task_format(
                raw_triton_output
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
            fallback_service = await self._handle_fallback_service(config.service_id, config)
            if fallback_service:
                self.logger.info("Attempting fallback NMT service")
                _, model_name, triton_endpoint, api_key, fallback_adapter_config = (
                    fallback_service
                )
                inference_model = NMTInferenceModel(adapter_config=fallback_adapter_config)
                triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
                    nmt_request.input, nmt_request.config.dict()
                )
                raw_triton_output = await self._call_triton_inference(
                    triton_endpoint, triton_inputs, triton_outputs, api_key
                )
                response_data = await inference_model.convert_triton_output_to_task_format(
                    raw_triton_output
                )
                postprocessed = await self.postprocess_output(response_data, source_texts)
                return NMTInferenceResponse(output=postprocessed['output'], smr_response=None)

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

        Returns:
            Tuple of (service_id, model_name, triton_endpoint, api_key, adapter_config).
        """
        service_id = config.service_id

        # If service_id not provided, could use SMR (Smart Model Router)
        # For now, default to configured service
        if not service_id:
            service_id = "indictrans-v2-all"
            self.logger.warning(f"No service_id provided, using default: {service_id}")

        # Resolve service using InferenceServerResolver
        self.logger.debug(f"Resolving service: {service_id}")
        try:
            service_info = await self.inference_server_resolver.resolve_service(service_id)
        except Exception as e:
            self.logger.error(
                f"Failed to resolve service {service_id}: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise RuntimeError(f"NMT: Failed to resolve service {service_id}: {str(e)}") from e

        # Extract fields from dict response
        model_name = service_info.get('name', '')
        triton_endpoint = service_info.get('endpoint', '')
        api_key = service_info.get('api_key')
        # adapter_config carries the tensor mapping (inputs/outputs) for this specific model
        adapter_config = service_info.get('adapter_config')

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                "NMT: Invalid service info from resolver: missing model_name or triton_endpoint"
            )

        return (service_id, model_name, triton_endpoint, api_key, adapter_config)

    async def _call_triton_inference(
        self,
        triton_endpoint: str,
        triton_inputs: List[Dict[str, Any]],
        triton_outputs: List[str],
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Triton inference server with prepared inputs.

        Args:
            triton_endpoint: Full inference URL provided by MMS (e.g. http://host/v2/models/nmt/infer)
            triton_inputs: KServe v2 formatted input list from convert_payload_to_triton_format()
            triton_outputs: Expected output tensor names
            api_key: Optional API key for auth

        Returns:
            Raw output from Triton

        Raises:
            RuntimeError: If Triton call fails
        """
        try:
            # Build Triton HTTP request
            infer_url = triton_endpoint

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
            self.logger.debug(f"Calling Triton: POST {infer_url}")
            return await HTTPServiceClient(timeout=300).post_json(infer_url, payload, headers)

        except Exception as e:
            self.logger.error(f"Failed to connect to Triton: {str(e)}")
            raise RuntimeError(f"Triton inference call failed at {triton_endpoint}: {str(e)}") from e

    async def _handle_fallback_service(
        self,
        primary_service_id: Optional[str],
        config: NMTConfig,
    ) -> Optional[Tuple[str, str, str, Optional[str], Optional[Any]]]:
        """
        Attempt to resolve a fallback service when the primary fails.

        Returns:
            Tuple of (service_id, model_name, triton_endpoint, api_key, adapter_config),
            or None if no fallback is available.
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
            model_name = service_info.get('name', '')
            triton_endpoint = service_info.get('endpoint', '')
            api_key = service_info.get('api_key')
            adapter_config = service_info.get('adapter_config')

            return (fallback_service_id, model_name, triton_endpoint, api_key, adapter_config)
        except Exception as e:
            self.logger.error(f"Fallback service resolution failed: {str(e)}")
            return None
