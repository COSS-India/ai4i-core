"""
ImageBase — base class for image-backed inference services.

Works on raw payload dicts (same contract as TextBase / BaseTaskService):
  validate_request   → ensures payload['image'] is non-empty and each item carries content/uri
  preprocess_input   → normalizes each item to base64 under 'image_content'
  get_payload_object → returns payload['image']; the base execute_triton_inference does the rest

All Triton I/O (payload assembly, output mapping) is handled by GenericTritonMapper
via the adapter_config sourced from MMS — concrete task services don't reimplement it.

Concrete task services (e.g. ImageDefaultModel) provide:
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

    def get_payload_object(self, payload: Dict[str, Any]) -> List[Any]:
        """Image input list lives under payload['image']."""
        return payload.get("image") or []

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


class ImageDefaultModel(ImageBase):
    """
    Concrete image model for generic-passthrough tasks (e.g. OCR).

    Inherits validation, base64 resolution, and adapter_config-driven Triton
    I/O from ImageBase. Output is returned as a generic dict — the route layer
    applies GenericInferenceResponse, so no task-specific subclassing is needed.
    Different tasks share this class; the adapter_config and Triton model name
    are what differ.
    """

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Unwrap Surya envelope → shape as {source: <extracted text>, target: ""}
        (NMT-style source/target pairing; target is empty for OCR).
        Bytes were already decoded to UTF-8 strings by GenericTritonMapper."""
        output_list = [
            {"source": self._unwrap_surya_envelope(item.get("text", "")), "target": ""}
            for item in response_items
        ]
        return {"output": output_list}

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return output + echo the request config verbatim. We deliberately
        do NOT synthesize language / textDetection here — those values should
        come from the model (Surya detects language) once the envelope is
        actually parsed for them. Faking defaults would lie about the source."""
        return {
            "output": postprocessed["output"],
            "config": payload.get("config"),
        }
