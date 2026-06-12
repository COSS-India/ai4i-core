"""
AudioBase — base class for all audio-backed inference services.

Covers: ASR, Audio Language Detection, Language Diarization, Speaker Diarization.

Inherits the BaseTaskService pipeline and sets:
  REQUIRED_ITEM_FIELDS → each item needs audioContent or audioUri
  preprocess_input      → base64 passthrough (downloads audioUri if needed)
  TRITON_CALL_MODE      → 'per_item': one Triton call per audio item

adapter_config value_paths read the item directly (input.audioContent), so no
context-builder hook is needed. The passthrough default fits tasks where Triton
decodes audio internally (ALD, Speaker Diarization, Language Diarization). ASR
is the exception: it needs float-PCM preprocessing and overrides preprocess_input
(reusing _get_audio_bytes here), writing input.samples for its config to read.

Request keys are camelCase (ULCA): audioContent, audioUri.
"""

import base64
from typing import Any, Dict, Optional

import httpx

from services.base.task_service import BaseTaskService


class AudioBase(BaseTaskService):
    """Base class for all audio inference services."""

    payload_key = "audio"  # audio input list lives under payload['audio']

    # Audio Triton models accept one file per request — run_inference loops
    # per item instead of one batch call.
    TRITON_CALL_MODE = "per_item"

    # Each audio item must carry inline content or a URI to download.
    REQUIRED_ITEM_FIELDS = (("audioContent", "audioUri"),)

    # ------------------------------------------------------------------
    # Preprocessing — base64 passthrough (default)
    # ------------------------------------------------------------------

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Pass each item through as-is. If only audioUri is provided, download
        and base64-encode it so the renderer always has audioContent.
        ASR overrides this with its float-PCM pipeline."""
        items = []
        for item in payload.get(self.payload_key) or []:
            d = item
            if not d.get("audioContent") and d.get("audioUri"):
                d = dict(d)
                d["audioContent"] = base64.b64encode(
                    await self._download_audio(str(d["audioUri"]))
                ).decode("utf-8")
            items.append(d)
        payload[self.payload_key] = items
        return payload

    # ------------------------------------------------------------------
    # Audio input helpers
    # ------------------------------------------------------------------

    async def _get_audio_bytes(self, audio_input: Dict[str, Any]) -> bytes:
        """Return raw audio bytes: base64-decode audioContent or download
        audioUri. Used by ASR's float-PCM preprocessing."""
        if audio_input.get("audioContent"):
            return base64.b64decode(audio_input["audioContent"])
        if audio_input.get("audioUri"):
            return await self._download_audio(str(audio_input["audioUri"]))
        raise ValueError(
            f"{self.task_name}: audio item must have audioContent or audioUri"
        )

    async def _download_audio(self, uri: str) -> bytes:
        """Download raw audio bytes from an HTTP/HTTPS URI.
        The URI is user-supplied — validated against the SSRF guard first."""
        from utils.url_guard import validate_external_url
        validate_external_url(uri)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(uri)
                response.raise_for_status()
                return response.content
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"{self.task_name}: timed out downloading audio from {uri}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"{self.task_name}: HTTP {exc.response.status_code} downloading audio from {uri}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"{self.task_name}: request error downloading audio from {uri}: {exc}"
            ) from exc
