"""ASR TaskService — Automatic Speech Recognition inference."""

import base64
from typing import Any, Dict, List, Tuple

from services.base.audio_base import AudioBase
from utils import audio_utils


class ASRTaskService(AudioBase):
    """
    TaskService for Automatic Speech Recognition.

    The only audio task that sends decoded float PCM to Triton — the
    AudioBase default (base64 passthrough) is overridden here:
      validate_request                  → adds sourceLanguage check
      preprocess_input                  → bytes → decode → mono → resample (16 kHz) → equalize
      convert_payload_to_triton_format  → normalises config.language, then super
      _triton_context_builder           → exposes audio.samples (not audio_content)
      postprocess                    → decode bytes → TranscriptionOutput list

    service_info (including adapter_config) is injected by the Orchestrator.
    """

    TARGET_SAMPLE_RATE = 16000  # All audio is resampled to this rate before Triton

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """AudioBase validation + sourceLanguage check."""
        await super().validate_request(payload)
        await self._validate_source_language(payload)

    async def _validate_source_language(self, payload: Dict[str, Any]) -> None:
        """
        Validate that sourceLanguage is present in the request config.
        Accepts both snake_case (source_language) and camelCase (sourceLanguage) keys.
        """
        config_dict = payload.get("config") or {}
        language = (
            config_dict.get("language") or {}
            if isinstance(config_dict, dict)
            else getattr(config_dict, "language", None) or {}
        )
        source_language = (
            language.get("source_language") or language.get("sourceLanguage")
            if isinstance(language, dict)
            else getattr(language, "source_language", None)
        )

        if not source_language:
            raise ValueError(
                f"{self.task_name}: config.language.sourceLanguage is required"
            )

    # ------------------------------------------------------------------
    # Preprocessing — float-PCM pipeline (overrides base64 passthrough)
    # ------------------------------------------------------------------

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Float-PCM preprocessing pipeline, applied to each item in sequence:
          1. Get raw audio bytes (base64 decode or URI download)
          2. _decode_audio_bytes → float32 numpy array + original sample rate
          3. _stereo_to_mono
          4. _resample to TARGET_SAMPLE_RATE
          5. _equalize_amplitude
        Returns list of item dicts enriched with samples / num_samples / sample_rate.
        """
        input_data = payload.get(self.payload_key) or []
        if not input_data:
            raise ValueError(f"{self.task_name}: audio list cannot be empty")
        items = []

        for item in input_data:
            d = item

            audio_bytes             = await self._get_audio_bytes(item)
            try:
                audio_data, sample_rate = audio_utils.decode_audio_bytes(audio_bytes)
            except ValueError as decode_err:
                raise ValueError(f"{self.task_name}: {decode_err}") from decode_err
            audio_data              = audio_utils.stereo_to_mono(audio_data)
            audio_data              = audio_utils.resample(audio_data, sample_rate, self.TARGET_SAMPLE_RATE)
            audio_data              = audio_utils.equalize_amplitude(audio_data)

            # samples must be a plain Python list — the config mapper's _cast_dtype
            # operates on Python lists, not numpy arrays.
            d["samples"]     = audio_data.tolist()
            d["num_samples"] = len(audio_data)
            d["sample_rate"] = self.TARGET_SAMPLE_RATE
            items.append(d)

        payload[self.payload_key] = items
        return payload

    # ------------------------------------------------------------------
    # Triton format hooks
    # ------------------------------------------------------------------

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Build KServe v2 inputs from preprocessed float PCM samples.

        Normalises config.language to always expose source_language (snake_case)
        so the adapter_config path 'request.config.language.source_language' resolves
        regardless of whether the frontend sends sourceLanguage (camelCase) or a
        plain language string.
        """
        config = dict(config)
        language = config.get("language", {})
        if isinstance(language, dict):
            source_lang = (
                language.get("source_language") or language.get("sourceLanguage") or ""
            )
            config["language"] = {"source_language": str(source_lang)}
        elif isinstance(language, str):
            config["language"] = {"source_language": language}

        return await super().convert_payload_to_triton_format(input_data, config)

    def _triton_context_builder(self):
        """
        Expose audio.samples / num_samples / sample_rate to value_path
        resolution — populated by preprocess_input before the Triton loop.
        """
        def build(item, index, config):
            samples = item.get("samples") or []
            return {
                "audio": {
                    "samples":     samples,
                    "num_samples": item.get("num_samples", len(samples)),
                    "sample_rate": item.get("sample_rate"),
                }
            }
        return build

    # ------------------------------------------------------------------
    # Audio decoding helpers (float-PCM path — ASR only)
    # ------------------------------------------------------------------

    async def _get_audio_bytes(self, audio_input: Any) -> bytes:
        """
        Extract raw audio bytes from an AudioInput item.
        Base64-decodes audioContent or downloads from audioUri.
        Returns raw bytes before any format decoding.
        Accepts both snake_case (audio_content) and camelCase (audioContent) keys.
        """
        audio_content = audio_input.get("audio_content") or audio_input.get("audioContent")
        audio_uri     = audio_input.get("audio_uri") or audio_input.get("audioUri")

        if audio_content:
            return base64.b64decode(audio_content)
        if audio_uri:
            return await self._download_audio(str(audio_uri))
        raise ValueError(
            f"{self.task_name}: audio item must have audio_content or audio_uri"
        )

    # postprocess_output: adapter_config-driven — the mapper decodes the
    # transcript from the Triton JSON (always a plain str; the old numpy/bytes
    # decode paths were unreachable on this pipeline), response_key renames
    # transcript -> output[].source per the ULCA ASR contract, and the
    # response envelope adds the constant nBestTokens: null. source_texts
    # (audio URIs) are intentionally unpaired: output[].source IS the
    # transcript for ASR.
