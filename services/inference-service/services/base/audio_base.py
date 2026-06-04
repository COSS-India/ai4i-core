"""
AudioBase — base class for all audio-backed inference services.

Covers: ASR, Audio Language Detection, Language Diarization, Speaker Diarization.

Inherits the BaseTaskService pipeline (process → validate → preprocess →
execute → postprocess) and overrides:
  validate_request          → common audio validation (audio items only)
  preprocess_input          → base64 passthrough (downloads audio_uri if needed)
  TRITON_CALL_MODE          → 'per_item': one Triton call per audio item
  convert_* hooks           → adapter_config-driven via GenericTritonMapper

The passthrough default fits tasks where Triton decodes audio internally
(ALD, Speaker Diarization, Language Diarization) — they extend this class
directly and implement postprocess. ASR is the exception: it needs
float-PCM preprocessing and overrides preprocess_input plus the convert
hooks in asr_service.py.

Task-specific helpers (e.g. _parse_json) live here but are NOT called from
the pipeline automatically — task services opt in by calling them in their
overrides.
"""

import base64
import json
import logging
from typing import Any, Dict, Optional

import httpx

from services.base.task_service import BaseTaskService

logger = logging.getLogger(__name__)


class AudioBase(BaseTaskService):
    """
    Base class for all audio inference services.
    Implements the common audio pipeline; task services extend only what differs.
    """

    payload_key = "audio"  # audio input list lives under payload['audio']

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """
        Common audio validation pipeline:
          1. Base null check (super)
          2. Audio list not empty, each item has audio_content or audio_uri

        Task-specific validation (e.g. ASR's sourceLanguage check) lives in
        the task service's validate_request override.
        """
        await super().validate_request(payload)
        await self._validate_audio_items(payload)

    # ------------------------------------------------------------------
    # Preprocessing — base64 passthrough (default)
    # ------------------------------------------------------------------

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        No float decode. Each item is passed through as-is.
        If only audioUri is provided, downloads and base64-encodes it
        so convert_payload_to_triton_format always has audio_content.

        ASR overrides this with its float-PCM pipeline (see asr_service.py).
        """
        input_data = payload.get(self.payload_key) or []
        if not input_data:
            raise ValueError(f"{self.task_name}: audio list cannot be empty")

        items = []
        for item in input_data:
            d = item if isinstance(item, dict) else item.model_dump(by_alias=False)
            has_content = d.get("audio_content") or d.get("audioContent")
            if not has_content:
                has_uri = d.get("audio_uri") or d.get("audioUri")
                if has_uri:
                    d = dict(d)
                    d["audio_content"] = await self._resolve_audio_base64(item)
            items.append(d)
        payload[self.payload_key] = items
        return payload

    # ------------------------------------------------------------------
    # Triton call topology + mapper context
    # ------------------------------------------------------------------

    # Audio Triton models accept one file per request — the generic
    # run_inference loops per item instead of one batch call.
    TRITON_CALL_MODE = "per_item"

    async def convert_payload_to_triton_format(self, input_data, config):
        """num_speakers defaults to "" so an adapter that declares a
        NUM_SPEAKERS tensor (speaker diarization) still resolves when the
        task config omits it — e.g. ALD can run against the sd-gpu model."""
        config = dict(config)
        if "num_speakers" not in config and "numSpeakers" not in config:
            config["num_speakers"] = ""
        return await super().convert_payload_to_triton_format(input_data, config)

    def _triton_context_builder(self):
        """Expose audio.audio_content (the base64 string) to value_path
        resolution. ASR overrides to expose float samples instead."""
        def build(item, index, config):
            audio_content = item.get("audio_content") or item.get("audioContent") or ""
            return {"audio": {"audio_content": audio_content}}
        return build

    # ------------------------------------------------------------------
    # Audio input helpers
    # ------------------------------------------------------------------

    async def _resolve_audio_base64(self, audio_input: Any) -> Optional[str]:
        """
        Return audio as a base64 string.
        Returns audioContent directly, or downloads from audioUri and base64-encodes.
        Accepts both snake_case (audio_content) and camelCase (audioContent) keys.
        """
        if isinstance(audio_input, dict):
            audio_content = audio_input.get("audio_content") or audio_input.get("audioContent")
            audio_uri     = audio_input.get("audio_uri") or audio_input.get("audioUri")
        else:
            audio_content = getattr(audio_input, "audio_content", None)
            audio_uri     = getattr(audio_input, "audio_uri", None)

        if audio_content:
            return audio_content
        if audio_uri:
            raw = await self._download_audio(str(audio_uri))
            return base64.b64encode(raw).decode("utf-8")
        return None

    async def _download_audio(self, uri: str) -> bytes:
        """
        Download raw audio bytes from an HTTP/HTTPS URI.
        The URI is user-supplied — validated against the SSRF guard first.
        Raises on non-2xx responses.
        """
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

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    async def _validate_audio_items(self, payload: Dict[str, Any]) -> None:
        """
        Validate that the audio list is not empty and each item
        has either audio_content or audio_uri.
        Common to all audio task types — called from validate_request pipeline.
        Accepts both snake_case (audio_content) and camelCase (audioContent) keys.
        """
        audio_items = payload.get("audio")
        if not audio_items:
            raise ValueError(f"{self.task_name}: audio list cannot be empty")

        for idx, item in enumerate(audio_items):
            if isinstance(item, dict):
                has_content = bool(item.get("audio_content") or item.get("audioContent"))
                has_uri     = bool(item.get("audio_uri") or item.get("audioUri"))
            else:
                has_content = bool(getattr(item, "audio_content", None))
                has_uri     = bool(getattr(item, "audio_uri", None))

            if not has_content and not has_uri:
                raise ValueError(
                    f"{self.task_name}: audio[{idx}] must have audio_content or audio_uri"
                )

    # ------------------------------------------------------------------
    # Output helpers — opt-in from task service postprocess
    # ------------------------------------------------------------------

    def _parse_json(self, value: Any) -> Dict[str, Any]:
        """Parse a Triton JSON-blob output value into a dict.

        Shared by the diarization tasks (DIARIZATION_RESULT tensor).
        Unwraps single-element list nesting from KServe v2 responses,
        decodes bytes, and returns {} on missing/unparseable input.
        """
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        # e.g. to_output_items peels [["json"]] → ["json"]; unwrap peels once more → "json"
        value = self.unwrap_output_value(value)
        if isinstance(value, str):
            try:
                return json.loads(value) or {}
            except json.JSONDecodeError:
                logger.warning("%s: failed to parse JSON output: %r", self.task_name, value[:200])
                return {}
        return {}
