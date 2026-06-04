"""
ImageBase — base class for image-backed inference services.

Works on raw payload dicts (same contract as TextBase / BaseTaskService):
  validate_request   → ensures payload['image'] is non-empty and each item carries content/uri
  preprocess_input   → normalizes each item to base64 under 'image_content'
  payload_key        → 'image'; the base run_inference does the rest

All Triton I/O (payload assembly, output mapping) is handled by GenericTritonMapper
via the adapter_config sourced from MMS — concrete task services don't reimplement it.

Concrete task services (e.g. OCRTaskService) provide:
  postprocess → output shaping + response envelope
"""

import base64
from typing import Any, Dict, List, Optional

import httpx

from services.base.task_service import BaseTaskService


class ImageBase(BaseTaskService):
    """Generic image task service base."""

    payload_key = "image"  # image input list lives under payload['image']

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

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize each image to base64 under 'image_content' (downloads URI if needed)."""
        items: List[Dict[str, Any]] = []
        for item in payload.get(self.payload_key) or []:
            d = dict(item) if isinstance(item, dict) else item
            d["image_content"] = await self._resolve_image_base64(d)
            items.append(d)
        payload[self.payload_key] = items
        return payload

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
        """Download raw image bytes from an HTTP(S) URI.
        The URI is user-supplied — validated against the SSRF guard first."""
        from utils.url_guard import validate_external_url
        validate_external_url(uri)
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
