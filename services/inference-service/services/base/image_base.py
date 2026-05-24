"""
ImageBase — base class for image-backed inference services.

Inherits the BaseTaskService.process template; overrides execute_triton_inference
to drive the image-specific Triton call (reads request.image, batches into a
single KServe v2 call using GenericTritonMapper + adapter_config).

Concrete task services (e.g. OCRTaskService) must implement:
  _deserialize_payload                              → typed request model
  _get_default_adapter_config                       → fallback when MMS returns null
  convert_payload_to_triton_format(items, config)   → (triton_inputs, output_names)
  convert_triton_output_to_task_format(raw_output)  → List[Dict] per image
  postprocess_output(response_items)                → response dict
  _build_response(request, postprocessed)           → typed response model

Mirrors AudioBase (services/base/audio_base.py).
"""

import base64
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel

from interfaces.task_service import BaseTaskService


class ImageBase(BaseTaskService):
    """Generic image task service base."""

    def __init__(
        self,
        service_info: Optional[Dict[str, Any]] = None,
        **dependencies: Any,
    ):
        super().__init__(service_info=service_info)
        self.logger = logging.getLogger(self.__class__.__module__)

    # ------------------------------------------------------------------
    # Pipeline hooks called by BaseTaskService.process
    # ------------------------------------------------------------------

    async def validate_request(self, request: BaseModel) -> None:
        """Common image validation: non-empty image list, each item has content or uri."""
        await super().validate_request(request)
        await self._validate_image_items(request)

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        """Normalize each image to base64 on image_content (downloads URI if needed)."""
        await super().preprocess_input(input_data)
        items: List[Dict[str, Any]] = []
        for item in input_data:
            d = item if isinstance(item, dict) else item.model_dump(by_alias=False)
            d["image_content"] = await self._resolve_image_base64(d)
            items.append(d)
        return items

    # ------------------------------------------------------------------
    # execute_triton_inference — image-shaped override
    # ------------------------------------------------------------------

    async def execute_triton_inference(
        self,
        config: Any,
        inference_model_class: type,
    ) -> Dict[str, Any]:
        """
        Image inference call — overrides BaseTaskService.execute_triton_inference.

        Differences from the text base:
          - Reads request.image (not request.input)
          - Batches all images into ONE Triton call (Surya supports batching;
            no per-item loop required, unlike audio's variable-length need)
          - Applies _get_default_adapter_config() when MMS returns null
          - convert_payload_to_triton_format / convert_triton_output_to_task_format
            are called on self (subclass methods), not on a separate mapper instance
        """
        del inference_model_class  # subclass hooks build the tensors

        service_id      = self.service_info.get("service_id", "")
        model_name      = self.service_info.get("name", "")
        triton_endpoint = self.service_info.get("endpoint", "")
        api_key         = self.service_info.get("api_key")
        adapter_config  = self.service_info.get("adapter_config")

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                f"{self.task_name}: service_info is missing 'name' or 'endpoint'. "
                "Ensure the Orchestrator resolved the service before creating this task service."
            )

        if not adapter_config:
            self.logger.warning(
                "%s: adapter_config missing from service_info — using default",
                self.task_name,
            )
            adapter_config = self._get_default_adapter_config()

        # Store so convert_payload_to_triton_format can access via self._adapter_config
        self._adapter_config = adapter_config

        request_payload = getattr(config, "_request_payload", None)
        if not request_payload:
            raise ValueError(f"{self.task_name}: config must have _request_payload set")

        image_items: List[Any] = getattr(request_payload, "image") or []
        self.logger.info(
            "%s: model=%s endpoint=%s inputs=%d",
            self.task_name, model_name, triton_endpoint, len(image_items),
        )

        items = [
            item if isinstance(item, dict) else item.model_dump(by_alias=False)
            for item in image_items
        ]
        config_dict = config.model_dump()

        triton_inputs, triton_outputs = await self.convert_payload_to_triton_format(
            items, config_dict
        )

        raw_output = await self._call_triton_inference(
            triton_endpoint=triton_endpoint,
            triton_inputs=triton_inputs,
            triton_outputs=triton_outputs,
            api_key=api_key,
        )

        response_data = await self.convert_triton_output_to_task_format(raw_output)
        return {
            "response_data": response_data,
            "source_texts": [],
            "service_id": service_id,
        }

    # ------------------------------------------------------------------
    # Hooks — subclasses must implement these
    # ------------------------------------------------------------------

    def _get_inference_model_class(self) -> type:
        """Return GenericTritonMapper — satisfies BaseTaskService.run_inference signature."""
        from services.base.config_mapper import GenericTritonMapper
        return GenericTritonMapper

    def _get_default_adapter_config(self) -> Dict[str, Any]:
        """Fallback adapter config when MMS returns null. Each concrete image task overrides."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _get_default_adapter_config"
        )

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Convert preprocessed image items + config into KServe v2 Triton inputs.
        self._adapter_config is available (set by execute_triton_inference)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement convert_payload_to_triton_format"
        )

    async def convert_triton_output_to_task_format(
        self, triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Convert raw Triton output into a list of task-specific result dicts.
        self._adapter_config is available (set by execute_triton_inference)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement convert_triton_output_to_task_format"
        )

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement postprocess_output"
        )

    def _build_response(
        self, request: BaseModel, postprocessed: Dict[str, Any]
    ) -> BaseModel:
        """Wrap postprocessed output in the typed response model.
        Called by run_inference after postprocess_output."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _build_response"
        )

    # ------------------------------------------------------------------
    # Image input helpers
    # ------------------------------------------------------------------

    async def _resolve_image_base64(self, image_input: Any) -> str:
        """Return image as a base64 string from inline content or downloaded from a URI."""
        if isinstance(image_input, dict):
            content = image_input.get("image_content")
            uri = image_input.get("image_uri")
        else:
            content = getattr(image_input, "image_content", None)
            uri = getattr(image_input, "image_uri", None)

        if content:
            return content
        if uri:
            raw = await self._download_image(str(uri))
            return base64.b64encode(raw).decode("utf-8")
        raise ValueError(f"{self.task_name}: image item has no image_content or image_uri")

    async def _download_image(self, uri: str) -> bytes:
        """Download raw image bytes from an HTTP(S) URI."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(uri)
                resp.raise_for_status()
                return resp.content
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"{self.task_name}: timed out downloading image from {uri}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"{self.task_name}: HTTP {exc.response.status_code} downloading image from {uri}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"{self.task_name}: request error downloading image from {uri}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    async def _validate_image_items(self, request: Any) -> None:
        """Image list non-empty; each item has image_content or image_uri."""
        items = getattr(request, "image", None)
        if not items:
            raise ValueError(f"{self.task_name}: image array cannot be empty")
        for idx, item in enumerate(items):
            if isinstance(item, dict):
                content = item.get("image_content")
                uri = item.get("image_uri")
            else:
                content = getattr(item, "image_content", None)
                uri = getattr(item, "image_uri", None)
            if not content and not uri:
                raise ValueError(
                    f"{self.task_name}: image[{idx}] requires image_content or image_uri"
                )

    # ------------------------------------------------------------------
    # Output decoding helpers
    # ------------------------------------------------------------------

    def _decode_text(self, value: Any) -> str:
        """Decode any output value to a UTF-8 string."""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if value is None:
            return ""
        return str(value)

    async def _decode_output_bytes(
        self, response_items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Decode every BYTES value in each response dict to a UTF-8 string."""
        decoded: List[Dict[str, Any]] = []
        for item in response_items:
            d: Dict[str, Any] = {}
            for key, value in item.items():
                d[key] = self._decode_text(value) if isinstance(value, (bytes, bytearray)) else value
            decoded.append(d)
        return decoded
