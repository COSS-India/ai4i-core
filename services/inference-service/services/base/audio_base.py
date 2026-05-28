"""
AudioBase — base class for all audio-backed inference services.

Covers: ASR, Audio Language Detection, Language Diarization, Speaker Diarization.

Inherits from BaseTaskService and implements the common audio pipeline:
  validate_request      → common audio validation (audio items only)
  preprocess_input      → decode → mono → resample → equalize → dequantize
  run_inference         → Template Method: resolve → Triton loop → postprocess → _build_response
  postprocess_output    → no common pipeline; model classes implement using helpers

Model classes must implement three hooks to participate in run_inference:
  convert_payload_to_triton_format(input_data, config) → (triton_inputs, triton_outputs)
  convert_triton_output_to_task_format(triton_output)  → List[Dict]
  _build_response(request, postprocessed)              → typed response model

Task-specific helpers (e.g. _validate_source_language, _wrap_transcription_output)
live here but are NOT called from the pipeline automatically — model classes
opt in by calling them in their overrides.
"""

import base64
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
import scipy.signal as sps

from interfaces.task_service import BaseTaskService
from ai4icore_core.telemetry import async_trace_stage

logger = logging.getLogger(__name__)


class AudioBase(BaseTaskService):
    """
    Base class for all audio inference services.
    Implements the common audio pipeline; model classes extend only what differs.
    """

    TARGET_SAMPLE_RATE = 16000  # All audio is resampled to this rate before Triton

    # ------------------------------------------------------------------
    # Pipeline entry points — self-contained raw-dict pipeline
    # ------------------------------------------------------------------

    async def process(self, payload: Dict[str, Any]) -> Any:
        """
        Audio inference pipeline (overrides BaseTaskService.process).

        Works with the raw request dict throughout — no Pydantic deserialization.
        This makes AudioBase self-contained regardless of whether the base class
        uses the typed-model (pre-PR #730) or raw-dict (post-PR #730) pattern.

        Flow:
          validate_request(payload)         — audio items present, language if required
          preprocess_input(payload['audio']) — decode / resample / equalize (or passthrough)
          run_inference(payload)             — Triton loop → postprocess → _build_response
        """
        payload = dict(payload)  # shallow copy — don't mutate caller's dict
        await self.validate_request(payload)
        audio_items = payload.get("audio")
        if audio_items:
            payload["audio"] = await self.preprocess_input(audio_items)
        return await self.run_inference(payload)

    async def run_inference(
        self,
        payload: Dict[str, Any],
    ) -> Any:
        """
        Audio inference runner (overrides BaseTaskService.run_inference).

        Calls execute_triton_inference directly with the raw payload dict —
        no config._request_payload indirection.
        """
        result = await self.execute_triton_inference(payload, self._get_inference_model_class())
        postprocessed = await self.postprocess_output(
            result["response_data"], source_texts=result["source_texts"]
        )
        return self._build_response(payload, postprocessed)

    def get_payload_object(self, payload: Dict[str, Any]) -> List[Any]:
        """Audio input list lives under payload['audio']."""
        return payload.get("audio") or []

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """
        Common audio validation pipeline:
          1. Base null check (super)
          2. Audio list not empty, each item has audio_content or audio_uri

        Task-specific validation (e.g. sourceLanguage) is opt-in —
        call _validate_source_language() in the model class override.
        """
        await super().validate_request(payload)
        await self._validate_audio_items(payload)

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        """
        Common audio preprocessing pipeline, applied to each item in sequence:
          1. Base empty check (super)
          2. Get raw audio bytes (base64 decode or URI download)
          3. _decode_audio_bytes → float32 numpy array + original sample rate
          4. _stereo_to_mono
          5. _resample to TARGET_SAMPLE_RATE
          6. _equalize_amplitude
          7. _dequantize_audio
        Returns list of item dicts enriched with samples / num_samples / sample_rate.
        """
        await super().preprocess_input(input_data)
        items = []

        for item in input_data:
            d = item if isinstance(item, dict) else item.model_dump(by_alias=False)

            audio_bytes            = await self._get_audio_bytes(item)
            audio_data, sample_rate = await self._decode_audio_bytes(audio_bytes)
            audio_data             = self._stereo_to_mono(audio_data)
            audio_data             = self._resample(audio_data, sample_rate, self.TARGET_SAMPLE_RATE)
            audio_seg              = self._equalize_amplitude(audio_data, self.TARGET_SAMPLE_RATE)
            audio_data             = self._dequantize_audio(audio_seg)

            # samples must be a plain Python list — the config mapper's _cast_dtype
            # operates on Python lists, not numpy arrays.
            d["samples"]     = audio_data.tolist()
            d["num_samples"] = len(audio_data)
            d["sample_rate"] = self.TARGET_SAMPLE_RATE
            items.append(d)

        return items

    # ------------------------------------------------------------------
    # execute_triton_inference — audio-specific override
    # ------------------------------------------------------------------

    @async_trace_stage("ai_inference")
    async def execute_triton_inference(
        self,
        payload: Dict[str, Any],
        inference_model_class: type,
    ) -> Dict[str, Any]:
        """
        Audio inference loop — overrides BaseTaskService.execute_triton_inference.

        Differences from the text base:
          - Reads payload['audio'] (not payload['input'])
          - Calls Triton once per audio item (one file per call)
          - Raises RuntimeError if adapter_config is missing from service_info
          - convert_payload_to_triton_format / convert_triton_output_to_task_format
            are called on self (model methods), not on a separate mapper instance

        VAD / chunk-batching is a future enhancement; add it here when ready.
        """
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
            raise RuntimeError(
                f"{self.task_name}: adapter_config missing from service_info. "
                "Every audio service must have an adapter_config seeded in mm_services."
            )

        # Store so convert_payload_to_triton_format can access via self._adapter_config
        self._adapter_config = adapter_config

        # Audio items are already preprocessed by process() via preprocess_input.
        # Config is the raw payload dict — field names match the schema (snake_case for ASR).
        audio_items: List[Any] = self.get_payload_object(payload)
        config_dict: Dict[str, Any] = payload.get("config") or {}
        all_response_data: List[Dict[str, Any]] = []

        for idx, audio_item in enumerate(audio_items):
            item_dict = (
                audio_item if isinstance(audio_item, dict)
                else audio_item.model_dump(by_alias=False)
            )

            triton_inputs, triton_outputs = await self.convert_payload_to_triton_format(
                [item_dict], config_dict
            )

            self.logger.debug(
                "%s: Triton call %d / %d  endpoint=%s",
                self.task_name, idx + 1, len(audio_items), triton_endpoint,
            )
            raw_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                triton_inputs=triton_inputs,
                triton_outputs=triton_outputs,
                api_key=api_key,
            )

            response_data = await self.convert_triton_output_to_task_format(raw_output)
            all_response_data.extend(response_data)

        # Collect audio URIs to surface as 'source' in postprocess_output (e.g. ASR).
        # Preprocessed items retain audio_uri / audioUri from the original request.
        source_uris = [
            (
                audio_item.get("audio_uri") or audio_item.get("audioUri") or ""
                if isinstance(audio_item, dict)
                else getattr(audio_item, "audio_uri", "") or ""
            )
            for audio_item in audio_items
        ]

        result = {
            "response_data": all_response_data,
            "source_texts": source_uris,
            "service_id": service_id,
        }
        return result

    # ------------------------------------------------------------------
    # Hooks — subclasses must implement these
    # ------------------------------------------------------------------

    def _get_inference_model_class(self) -> type:
        """Return GenericTritonMapper — satisfies BaseTaskService.run_inference signature."""
        from services.base.config_mapper import GenericTritonMapper
        return GenericTritonMapper

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Convert preprocessed audio item(s) + config into KServe v2 Triton inputs.
        self._adapter_config is available (set by run_inference before the loop).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement convert_payload_to_triton_format"
        )

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert raw Triton output into a list of task-specific result dicts.
        self._adapter_config is available (set by run_inference before the loop).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement convert_triton_output_to_task_format"
        )

    def _build_response(
        self, payload: Any, postprocessed: Dict[str, Any]
    ) -> Any:
        """
        Response-builder hook: wrap postprocessed output in the typed response model.

        Called by run_inference after postprocess_output.
        Every concrete model class must implement this.

        Example:
            def _build_response(self, payload, postprocessed):
                return ASRInferenceResponse(output=postprocessed["output"])
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _build_response"
        )

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        """
        No common postprocess pipeline — each task handles this differently.
        Model classes implement using the output helpers below
        (_decode_output_bytes, _wrap_transcription_output, _empty_output).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement postprocess_output"
        )

    # ------------------------------------------------------------------
    # Audio input helpers
    # ------------------------------------------------------------------

    async def _get_audio_bytes(self, audio_input: Any) -> bytes:
        """
        Extract raw audio bytes from an AudioInput item.
        Base64-decodes audioContent or downloads from audioUri.
        Returns raw bytes before any format decoding.
        Accepts both snake_case (audio_content) and camelCase (audioContent) keys.
        """
        if isinstance(audio_input, dict):
            audio_content = audio_input.get("audio_content") or audio_input.get("audioContent")
            audio_uri     = audio_input.get("audio_uri") or audio_input.get("audioUri")
        else:
            audio_content = getattr(audio_input, "audio_content", None)
            audio_uri     = getattr(audio_input, "audio_uri", None)

        if audio_content:
            return base64.b64decode(audio_content)
        if audio_uri:
            return await self._download_audio(str(audio_uri))
        raise ValueError(
            f"{self.task_name}: audio item must have audio_content or audio_uri"
        )

    async def _decode_audio_bytes(
        self, audio_bytes: bytes
    ) -> Tuple[Any, int]:
        """
        Decode raw audio bytes → (float32 numpy array, sample_rate).
        Uses soundfile as primary decoder; falls back to raw PCM for unsupported formats.
        """
        try:
            import soundfile as sf
            audio_data, sample_rate = sf.read(
                BytesIO(audio_bytes), dtype="float32", always_2d=False
            )
            return audio_data, sample_rate
        except Exception as sf_err:
            logger.warning(
                "soundfile failed to decode audio (%s), falling back to raw PCM", sf_err
            )
            # Fallback: treat raw bytes as little-endian int16 PCM at 16kHz
            try:
                audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                return audio_data, 16000
            except Exception as pcm_err:
                logger.error("Failed to decode audio: %s", pcm_err)
                raise RuntimeError(
                    f"{self.task_name}: unable to decode audio bytes"
                ) from pcm_err

    async def _resolve_audio_base64(self, audio_input: Any) -> Optional[str]:
        """
        Return audio as a base64 string.
        Returns audioContent directly, or downloads from audioUri and base64-encodes.
        Used by services that send base64 directly to Triton (ALD, Language Diarization, etc.).
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

    async def _decode_audio_items(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        """
        Decode each audio item to float32 PCM samples.
        Populates 'samples', 'num_samples', and 'sample_rate' on every item dict.
        Used by ASR (sends float arrays to Triton).
        Skips amplitude equalization — use preprocess_input for the full pipeline.
        """
        items = []
        for item in input_data:
            if hasattr(item, "model_dump"):
                d = item.model_dump(by_alias=False)
            elif hasattr(item, "dict"):
                d = item.dict()
            elif isinstance(item, dict):
                d = dict(item)
            else:
                d = dict(item.__dict__)

            audio_content = d.get("audio_content")
            audio_uri     = d.get("audio_uri")
            target_rate   = d.get("sample_rate") or 16000

            samples, actual_rate = await self._decode_audio(
                audio_content, audio_uri, target_rate
            )
            d["samples"]     = samples
            d["num_samples"] = len(samples)
            d["sample_rate"] = actual_rate
            items.append(d)
        return items

    async def _decode_audio(
        self,
        audio_content: Optional[str],
        audio_uri: Optional[str],
        target_rate: int,
    ) -> Tuple[Any, int]:
        """
        Decode a single audio input from base64 string or HTTP URI.
        Returns (float32 numpy array, sample_rate).
        Uses soundfile if available; falls back to raw int16 PCM.
        """
        if audio_content:
            raw = base64.b64decode(audio_content)
        elif audio_uri:
            raw = await self._download_audio(str(audio_uri))
        else:
            raise ValueError(
                f"{self.task_name}: audio item must have audio_content or audio_uri"
            )

        try:
            import soundfile as sf
            data, rate = sf.read(BytesIO(raw), dtype="float32", always_2d=False)
            if data.ndim == 2:
                data = data.mean(axis=1)
        except Exception:
            # Fallback: treat raw bytes as little-endian int16 PCM
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rate = target_rate

        if rate != target_rate:
            data = self._resample(data, rate, target_rate)

        return data.astype(np.float32), target_rate

    # ------------------------------------------------------------------
    # Audio processing helpers
    # ------------------------------------------------------------------

    def _stereo_to_mono(self, audio: Any) -> Any:
        """
        Convert stereo audio to mono by averaging channels.
        No-op if audio is already mono.
        """
        if isinstance(audio, np.ndarray) and audio.ndim > 1:
            return audio.mean(axis=1).astype(np.float32)
        return audio

    def _resample(self, data: Any, from_rate: int, to_rate: int) -> Any:
        """
        Resample a float32 numpy array from from_rate to to_rate.
        No-op if rates are equal.
        """
        if from_rate == to_rate:
            return data
        num_samples = round(len(data) * float(to_rate) / from_rate)
        resampled = sps.resample(data, num_samples)
        return resampled.astype(np.float32)

    def _equalize_amplitude(self, audio: Any, frame_rate: int) -> Any:
        """
        Normalize audio amplitude using numpy operations.
        Returns normalized float32 numpy array.
        """
        # Normalize to [-1, 1] range
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio_normalized = audio / max_val
        else:
            audio_normalized = audio
        return audio_normalized.astype(np.float32)

    def _dequantize_audio(self, audio_data: Any) -> Any:
        """
        Return normalized float32 audio data.
        Since _equalize_amplitude now returns float32 directly, this is a pass-through.
        """
        return audio_data.astype(np.float32)

    async def _download_audio(self, uri: str) -> bytes:
        """
        Download raw audio bytes from an HTTP/HTTPS URI.
        Raises on non-2xx responses.
        """
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

    async def _validate_source_language(self, payload: Dict[str, Any]) -> None:
        """
        Validate that sourceLanguage is present in the request config.
        Opt-in — not called from base pipeline.
        Call from model class validate_request override (e.g. ASRTaskService).
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
    # Output / postprocess helpers
    # ------------------------------------------------------------------

    async def _decode_transcript(self, transcript: Any) -> str:
        """
        Decode a transcript value to a UTF-8 string.
        Handles bytes, numpy arrays, and plain strings uniformly.
        """
        if isinstance(transcript, bytes):
            return transcript.decode("utf-8")
        if isinstance(transcript, np.ndarray):
            if transcript.dtype == object:
                return str(transcript.item())
            if transcript.size > 0:
                if transcript.dtype == np.uint8:
                    return transcript.tobytes().decode("utf-8")
                return str(transcript.item())
            return ""
        if isinstance(transcript, (str, np.str_)):
            return str(transcript)
        return str(transcript)

    async def _decode_output_bytes(
        self, response_items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Decode all BYTES output values in a list of response dicts to UTF-8 strings.
        Calls _decode_transcript() per item.
        Opt-in — called from model class postprocess_output override.
        """
        decoded = []
        for item in response_items:
            d = dict(item) if isinstance(item, dict) else {}
            for key, value in d.items():
                if isinstance(value, (bytes, np.ndarray)):
                    d[key] = await self._decode_transcript(value)
            decoded.append(d)
        return decoded

    async def _wrap_transcription_output(
        self,
        decoded_items: List[Dict[str, Any]],
        source_texts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Wrap decoded transcript strings in TranscriptionOutput.
        Returns {"output": [TranscriptionOutput, ...]}.
        Opt-in — not called from base pipeline.
        Call from model class postprocess_output override (e.g. ASRTaskService).

        source_texts: parallel list of audio URIs (or empty strings) collected by
        execute_triton_inference; used to populate TranscriptionOutput.source so
        the frontend can identify which audio item each transcript belongs to.
        """
        output = []
        for item in decoded_items:
            transcript = item.get("transcript", item.get("source", ""))
            n_best = item.get("nBestTokens", item.get("n_best_tokens"))
            output.append({"source": str(transcript), "nBestTokens": n_best})
        return {"output": output}

    async def _empty_output(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Return a safe empty output dict for the calling task type.
        Used as a fallback when audio is missing or inference fails.
        kwargs allow task-specific fields (e.g. target_language for Lang Diarization).
        """
        return {"output": []}

    # ------------------------------------------------------------------
    # Transcript format helpers
    # ------------------------------------------------------------------

    def _count_words(self, text: str) -> int:
        """Count the number of words in a transcript string."""
        try:
            return len([w for w in text.split() if w.strip()])
        except Exception:
            return 0

    def _format_as_srt(self, transcript_lines: List[Dict[str, Any]]) -> str:
        """
        Format transcript lines with timecodes as an SRT subtitle file.
        Each line dict expects 'start', 'end', and 'text' keys.
        """
        srt_content = []
        for i, line in enumerate(transcript_lines, 1):
            start_ts = self._format_timestamp(line.get("start", 0))
            end_ts   = self._format_timestamp(line.get("end", 0))
            srt_content.append(str(i))
            srt_content.append(f"{start_ts} --> {end_ts}")
            srt_content.append(line.get("text", ""))
            srt_content.append("")
        return "\n".join(srt_content)

    def _format_as_webvtt(self, transcript_lines: List[Dict[str, Any]]) -> str:
        """
        Format transcript lines with timecodes as a WebVTT file.
        Each line dict expects 'start', 'end', and 'text' keys.
        """
        webvtt_content = ["WEBVTT", ""]
        for line in transcript_lines:
            start_ts = self._format_webvtt_timestamp(line.get("start", 0))
            end_ts   = self._format_webvtt_timestamp(line.get("end", 0))
            webvtt_content.append(f"{start_ts} --> {end_ts}")
            webvtt_content.append(line.get("text", ""))
            webvtt_content.append("")
        return "\n".join(webvtt_content)

    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
        hours     = int(seconds // 3600)
        minutes   = int((seconds % 3600) // 60)
        secs      = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

    def _format_webvtt_timestamp(self, seconds: float) -> str:
        """Convert seconds to WebVTT timestamp format: HH:MM:SS.mmm"""
        hours     = int(seconds // 3600)
        minutes   = int((seconds % 3600) // 60)
        secs      = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millisecs:03d}"
