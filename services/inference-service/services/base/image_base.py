"""
ImageBase — base class for all image-backed inference services.

Covers: OCR, Document Layout, Vision, and other future image tasks.

Inherits from BaseTaskService and implements the common image pipeline:
  validate_request      → common image validation (image items only)
  preprocess_input      → common image preprocessing pipeline
  run_inference         → resolve → build mapper → batched Triton call → postprocess
  postprocess_output    → no common pipeline; model classes implement

Task-specific helpers (e.g. _validate_language_hint, _build_image_context)
live here but are NOT called from the pipeline automatically — model classes
opt in by calling them in their overrides.
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from interfaces.task_service import BaseTaskService


class ImageBase(BaseTaskService):
    """
    Base class for all image inference services.
    Implements the common image pipeline; model classes extend only what differs.
    """

    def __init__(self, **dependencies: Any):
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__module__)

    # ------------------------------------------------------------------
    # Pipeline methods
    # ------------------------------------------------------------------

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> BaseModel:
        """
        ABC stub: image routes deserialize the request body via FastAPI,
        so this method is never invoked at runtime. Present only to satisfy
        ITaskService's abstract contract so subclasses can be instantiated.
        """
        ...

    async def validate_request(self, request: BaseModel) -> None:
        """
        Common image validation pipeline:
          1. Base null check (super)
          2. Image list not empty, each item has image_content or image_uri

        Task-specific validation (e.g. language hint) is opt-in —
        call _validate_language_hint() in the model class override.
        """
        await super().validate_request(request)
        await self._validate_image_items(request)

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        """
        Common image preprocessing:
          1. Base empty check (super)
          2. Resolve each image as base64 (decode inline content or download from URI)
        Returns list of item dicts enriched with 'data_b64'.
        """
        await super().preprocess_input(input_data)

        items = await self._resolve_image_base64(input_data)
        self.logger.debug(f"Image preprocessed {len(items)} inputs")
        return items

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Any:
        """
        Override in model class — wrap mapper output items in the task-specific
        response model (e.g. OCRInferenceResponse).
        """
        ...

    # ------------------------------------------------------------------
    # Service resolution
    # ------------------------------------------------------------------

    async def _resolve_service_and_model(
        self, config: Any
    ) -> Tuple[str, str, str, Optional[str], Optional[Any]]:
        """
        Resolve Triton endpoint + adapter_config from Model Management.
        Model classes may override to inject a default adapter_config when the
        service info doesn't carry one.
        """
        service_id = config.service_id
        try:
            service_info = await self.inference_server_resolver.resolve_service(service_id)
        except Exception as e:
            raise RuntimeError(
                f"Image task: Failed to resolve service {service_id}: {e}"
            ) from e

        model_name = service_info.get("name", "")
        triton_endpoint = service_info.get("endpoint", "")
        api_key = service_info.get("api_key")
        adapter_config = service_info.get("adapter_config")

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                "Image task: Invalid service info from resolver: missing model_name or triton_endpoint"
            )

        return (service_id, model_name, triton_endpoint, api_key, adapter_config)

    # ------------------------------------------------------------------
    # Image input helpers (concrete)
    # Always return base64
    # ------------------------------------------------------------------

    async def _resolve_image_base64(self, image_input: Any) -> str:
        """Return image as a base64 string from inline content or downloaded from a URI."""
        content = image_input.get("image_content") if isinstance(image_input, dict) else getattr(image_input, "image_content", None)
        uri = image_input.get("image_uri") if isinstance(image_input, dict) else getattr(image_input, "image_uri", None)

        if content:
            return content
        if uri:
            raw = await self._download_image(uri)
            return base64.b64encode(raw).decode("utf-8")
        raise ValueError("Image input has no image_content or image_uri")

    async def _download_image(self, uri: str) -> bytes:
        """Download raw image bytes from an HTTP(S) URI."""
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(uri)
            resp.raise_for_status()
            return resp.content

    async def _get_image_bytes(self, image_input: Any) -> bytes:
        """Raw image bytes — base64-decode inline content or download from URI."""
        content = image_input.get("image_content") if isinstance(image_input, dict) else getattr(image_input, "image_content", None)
        uri = image_input.get("image_uri") if isinstance(image_input, dict) else getattr(image_input, "image_uri", None)
        if content:
            return base64.b64decode(content)
        if uri:
            return await self._download_image(uri)
        raise ValueError("Image input has no image_content or image_uri")

    # ------------------------------------------------------------------
    # Image processing helpers (stub — fill when first vision task arrives)
    # ------------------------------------------------------------------

    def _decode_image(self, image_bytes: bytes) -> Any:
        """Decode raw image bytes into a pixel array. Stub — Pillow integration."""
        ...

    def _resize_image(self, image: Any, target_width: int, target_height: int) -> Any:
        """Resize a pixel array. Stub."""
        ...

    def _normalize_pixels(self, image: Any) -> Any:
        """Normalize pixel values to [0,1] float32. Stub."""
        ...

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    async def _validate_image_items(self, request: Any) -> None:
        """Image list non-empty + each item has image_content or image_uri."""
        items = getattr(request, "image", None)
        if not items:
            raise ValueError(f"{self.task_name}: image array cannot be empty")
        for idx, item in enumerate(items):
            content = getattr(item, "image_content", None) if not isinstance(item, dict) else item.get("image_content")
            uri = getattr(item, "image_uri", None) if not isinstance(item, dict) else item.get("image_uri")
            if not content and not uri:
                raise ValueError(
                    f"{self.task_name}: image[{idx}] requires image_content or image_uri"
                )

    async def _validate_language_hint(self, request: Any) -> None:
        """Opt-in: enforce language hint on the request config. No-op base impl."""
        ...

    # ------------------------------------------------------------------
    # Output / postprocess helpers (concrete)
    # ------------------------------------------------------------------

    def _decode_text(self, value: Any) -> str:
        """Decode any output value to a UTF-8 string (bytes / str passthrough)."""
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
                if isinstance(value, (bytes, bytearray)):
                    d[key] = self._decode_text(value)
                else:
                    d[key] = value
            decoded.append(d)
        return decoded

    # ------------------------------------------------------------------
    # Task-specific hooks (model classes override)
    # ------------------------------------------------------------------

    async def _wrap_text_output(
        self, decoded_items: List[Dict[str, Any]]
    ) -> Any:
        """Override in model class — wrap decoded text in task-specific response model."""
        ...

    async def _wrap_layout_output(
        self, decoded_items: List[Dict[str, Any]]
    ) -> Any:
        """Override in model class — wrap layout/bounding-box payloads."""
        ...

    async def _empty_output(self, **kwargs: Any) -> Any:
        """Override in model class — return a safe empty response on failure."""
        ...

    # ------------------------------------------------------------------
    # OCR-style output helpers (concrete; used by OCRDefaultModel)
    # ------------------------------------------------------------------

    def _unwrap_surya_envelope(self, raw_text: Any) -> str:
        """
        Surya ensembles return a JSON envelope per image with a 'full_text' field.
        Unwrap when present; return the value as-is otherwise.
        """
        text = self._decode_text(raw_text)
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "full_text" in parsed:
                    return str(parsed.get("full_text", ""))
            except json.JSONDecodeError:
                pass
        return text
