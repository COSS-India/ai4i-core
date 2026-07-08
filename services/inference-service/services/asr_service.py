"""ASR TaskService — Automatic Speech Recognition inference."""

import asyncio
import base64
from io import BytesIO
from math import gcd
from typing import Any, Dict, List, Tuple

import numpy as np
import scipy.signal as sps

from services.base.audio_base import AudioBase

# Cap concurrent decode + resample work across all in-flight requests. Each job
# holds several MB of numpy arrays; without a bound, a burst of parallel
# requests stacks that memory at once on a pod with no memory limit. The pod is
# also single-core, so extra threads past this only add scheduler churn.
_PREPROCESS_MAX_CONCURRENCY = 4
_preprocess_semaphore = asyncio.Semaphore(_PREPROCESS_MAX_CONCURRENCY)


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
        Float-PCM preprocessing pipeline:
          1. Fetch raw audio bytes for all items (async — supports URI downloads)
          2. Offload CPU-bound work to thread pool per item so the event loop
             is free to serve other requests during soundfile decode + resample
        Items are returned with samples as a Python list (converted in the
        thread) so the event loop is not blocked by .tolist() or mapper overhead.
        """
        input_data = payload.get(self.payload_key) or []
        if not input_data:
            raise ValueError(f"{self.task_name}: audio list cannot be empty")

        # Concurrent URI downloads (base64 items resolve instantly)
        audio_bytes_list = await asyncio.gather(
            *[self._get_audio_bytes(item) for item in input_data]
        )

        # CPU-bound decode + resample in thread pool, bounded by the semaphore
        # so parallel requests don't stack unbounded numpy arrays in memory.
        processed = await asyncio.gather(
            *[
                self._preprocess_item(item, ab)
                for item, ab in zip(input_data, audio_bytes_list)
            ]
        )

        payload[self.payload_key] = list(processed)
        return payload

    async def _preprocess_item(self, item: Dict[str, Any], audio_bytes: bytes) -> Dict[str, Any]:
        """Run one item's CPU-bound preprocessing in a bounded thread-pool slot."""
        async with _preprocess_semaphore:
            return await asyncio.to_thread(self._preprocess_item_sync, item, audio_bytes)

    def _preprocess_item_sync(self, item: Dict[str, Any], audio_bytes: bytes) -> Dict[str, Any]:
        """Sync preprocessing pipeline — runs in a thread-pool worker.

        Converts samples to a Python list here (in the thread) so the event loop
        is not blocked by the 100–200 ms .tolist() allocation and so the
        _materialize_tensor fast-path (plain list comprehension, no per-element
        function calls) fires correctly in the config mapper.
        """
        audio_data, sample_rate = self._decode_audio_bytes_sync(audio_bytes)
        audio_data = self._stereo_to_mono(audio_data)
        audio_data = self._resample(audio_data, sample_rate, self.TARGET_SAMPLE_RATE)
        audio_data = self._equalize_amplitude(audio_data)
        item["samples"]     = audio_data.tolist()  # convert in thread, not on event loop
        item["num_samples"] = len(audio_data)
        item["sample_rate"] = self.TARGET_SAMPLE_RATE
        return item

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
            samples = item.get("samples")
            if samples is None:
                samples = []
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

    async def _decode_audio_bytes(self, audio_bytes: bytes) -> Tuple[Any, int]:
        """Async wrapper kept for backward compatibility with tests."""
        return self._decode_audio_bytes_sync(audio_bytes)

    def _decode_audio_bytes_sync(self, audio_bytes: bytes) -> Tuple[Any, int]:
        """Decode raw audio bytes → (float32 numpy array, sample_rate).

        Sync so it can be called from a thread-pool worker via asyncio.to_thread.
        No fallback on decode failure: silently reinterpreting undecodable bytes
        as raw PCM produced "valid" noise that transcribed to garbage.
        """
        try:
            import soundfile as sf
            audio_data, sample_rate = sf.read(
                BytesIO(audio_bytes), dtype="float32", always_2d=False
            )
            return audio_data, sample_rate
        except Exception as sf_err:
            raise ValueError(
                f"{self.task_name}: unable to decode audio "
                f"(expected a valid wav/flac/ogg stream): {sf_err}"
            ) from sf_err

    def _stereo_to_mono(self, audio: Any) -> Any:
        """
        Convert stereo audio to mono by averaging channels.
        No-op if audio is already mono.
        """
        if isinstance(audio, np.ndarray) and audio.ndim > 1:
            return audio.mean(axis=1).astype(np.float32)
        return audio

    def _resample(self, data: Any, from_rate: int, to_rate: int) -> Any:
        """Resample a float32 numpy array from from_rate to to_rate.

        resample_poly is faster only when the GCD-reduced ratio has a small
        denominator (≤20 phases, e.g. 48000→16000 gives down=3).  For complex
        ratios like 44100→16000 (down=441 after GCD) it builds an 8821-tap FIR
        which is slower than an FFT over the same signal — so fall back to
        scipy.signal.resample (FFT-based) in that case.
        """
        if from_rate == to_rate:
            return data
        g = gcd(int(from_rate), int(to_rate))
        up   = to_rate  // g
        down = from_rate // g
        if down <= 20:
            resampled = sps.resample_poly(data, up, down)
        else:
            num_samples = round(len(data) * to_rate / from_rate)
            resampled = sps.resample(data, num_samples)
        return resampled.astype(np.float32)

    def _equalize_amplitude(self, audio: Any) -> Any:
        """
        Normalize audio amplitude to the [-1, 1] range.
        Returns normalized float32 numpy array.
        """
        audio = audio.astype(np.float32, copy=False)
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            # In place: we own this array (fresh from resample/decode), so avoid
            # allocating another full copy per request.
            audio *= np.float32(1.0 / max_val)
        return audio

    # postprocess_output: adapter_config-driven — the mapper decodes the
    # transcript from the Triton JSON (always a plain str; the old numpy/bytes
    # decode paths were unreachable on this pipeline), response_key renames
    # transcript -> output[].source per the ULCA ASR contract, and the
    # response envelope adds the constant nBestTokens: null. source_texts
    # (audio URIs) are intentionally unpaired: output[].source IS the
    # transcript for ASR.
