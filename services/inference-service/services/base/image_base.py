"""
ImageBase — base class for image-backed inference services.

Adds image-specific pieces to the generic BaseTaskService pipeline:
  validate_request   → ensures the image list is non-empty and each item carries content/uri
  preprocess_input   → normalizes each item to base64 image_content (downloads URI if needed)
  _get_request_input → exposes `request.image` to BaseTaskService.execute_triton_inference

All Triton I/O (payload assembly, output mapping) is handled by GenericTritonMapper
via the adapter_config sourced from MMS — concrete task services don't reimplement it.

Concrete task services (e.g. OCRTaskService) typically provide:
  REQUEST_SCHEMA       → pydantic request model for the base deserializer
  postprocess_output   → response shaping
  _build_response      → typed response model
"""

import base64
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

    async def validate_request(self, request: Any) -> None:
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

    def _get_request_input(self, request: Any) -> List[Any]:
        """Image tasks carry their items on `request.image`."""
        return getattr(request, "image", []) or []

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
