"""
ImageBase — base class for image-backed inference services.

Works on raw payload dicts (same contract as TextBase / BaseTaskService):
  validate_request   → ensures payload['image'] is non-empty and each item carries content/uri
  preprocess_input   → normalizes each item to base64 under 'image_content'
  INPUT_KEY="image"  → execute_triton_inference (overridden here) reads payload['image']

All Triton I/O (payload assembly, output mapping) is handled by GenericTritonMapper
via the adapter_config sourced from MMS — concrete task services don't reimplement it.

Concrete task services (e.g. OCRTaskService) provide:
  postprocess_output → response shaping
  _build_response    → typed response model
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from interfaces.task_service import BaseTaskService


class ImageBase(BaseTaskService):
    """Generic image task service base."""

    INPUT_KEY = "image"

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

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """Common image validation: non-empty image list, each item has content or uri."""
        await super().validate_request(payload)

        items = payload.get("image")
        if not items:
            raise ValueError(f"{self.task_name}: image array cannot be empty")
        for idx, item in enumerate(items):
            if not self._item_content(item) and not self._item_uri(item):
                raise ValueError(
                    f"{self.task_name}: image[{idx}] requires imageContent or imageUri"
                )

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        """Normalize each image to base64 under 'image_content' (downloads URI if needed)."""
        await super().preprocess_input(input_data)
        items: List[Dict[str, Any]] = []
        for item in input_data:
            d = dict(item) if isinstance(item, dict) else item
            d["image_content"] = await self._resolve_image_base64(d)
            items.append(d)
        return items

    async def execute_triton_inference(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Image inference — overrides BaseTaskService.execute_triton_inference,
        which is hardcoded to payload['input']. Reads payload[self.INPUT_KEY]
        ('image') instead; Triton I/O is driven by adapter_config via
        GenericTritonMapper (concrete task services don't reimplement it).
        """
        try:
            service_id = self.service_info.get("service_id", "")
            model_name = self.service_info.get("name", "")
            triton_endpoint = self.service_info.get("endpoint", "")
            api_key = self.service_info.get("api_key")
            adapter_config = self.service_info.get("adapter_config")

            if not model_name or not triton_endpoint:
                raise RuntimeError(
                    f"{self.task_name}: service_info is missing 'name' or 'endpoint'. "
                    "Ensure the Orchestrator resolved the service before creating this task service."
                )

            from services.base.config_mapper import GenericTritonMapper
            inference_model = GenericTritonMapper(adapter_config=adapter_config)

            input_items = payload.get(self.INPUT_KEY, [])
            config_data = payload.get("config", {})

            if not input_items:
                raise ValueError(
                    f"{self.task_name}: payload '{self.INPUT_KEY}' is empty or missing"
                )

            triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
                input_items, config_data
            )

            self.logger.info(f"Calling Triton inference server: {triton_endpoint}")
            raw_triton_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                triton_inputs=triton_inputs,
                triton_outputs=triton_outputs,
                api_key=api_key,
            )

            response_data = await inference_model.convert_triton_output_to_task_format(
                raw_triton_output
            )

            return {
                "response_data": response_data,
                "source_texts": [],
                "service_id": service_id,
            }
        except Exception as e:
            self.logger.error(f"Triton inference execution failed: {str(e)}", exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Image input helpers
    # ------------------------------------------------------------------

    def _item_content(self, item: Any) -> Optional[str]:
        if isinstance(item, dict):
            return item.get("imageContent") or item.get("image_content")
        return getattr(item, "image_content", None)

    def _item_uri(self, item: Any) -> Optional[str]:
        if isinstance(item, dict):
            return item.get("imageUri") or item.get("image_uri")
        return getattr(item, "image_uri", None)

    async def _resolve_image_base64(self, image_input: Any) -> str:
        """Return image as a base64 string from inline content or downloaded from a URI."""
        content = self._item_content(image_input)
        uri = self._item_uri(image_input)
        if content:
            return content
        if uri:
            raw = await self._download_image(str(uri))
            return base64.b64encode(raw).decode("utf-8")
        raise ValueError(f"{self.task_name}: image item has no imageContent or imageUri")

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
    # Output decoding helper
    # ------------------------------------------------------------------

    def _decode_text(self, value: Any) -> str:
        """Decode any output value to a UTF-8 string."""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if value is None:
            return ""
        return str(value)

    def _unwrap_surya_envelope(self, raw_text: Any) -> str:
        """
        Surya ensembles return a JSON envelope per image with a 'full_text' field.
        Unwrap when present; return the value as-is otherwise.
        """
        text = self._decode_text(raw_text)
        if text.lstrip().startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "full_text" in parsed:
                    return str(parsed.get("full_text", ""))
            except json.JSONDecodeError:
                pass
        return text
