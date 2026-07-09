"""TTS (Text-to-Speech) TaskService implementation."""

import asyncio
import base64
from io import BytesIO
from math import gcd
from typing import Any, Dict, List

import numpy as np
import scipy.io.wavfile as wav_io
import scipy.signal as sps

from services.base.text_base import TextBase
from pydub import AudioSegment

# Triton model always outputs at this rate
_TRITON_SAMPLE_RATE = 22050
# Maximum characters per Triton call
_MAX_CHUNK_LENGTH = 400
# Bounds for user-controlled numerics (OWASP API4 — resource consumption):
# samplingRate outside telephony..studio range is rejected; audioDuration
# drives silence padding, so an unbounded value would allocate GBs.
_MIN_SAMPLE_RATE = 8000
_MAX_SAMPLE_RATE = 48000
_MAX_AUDIO_DURATION_S = 300.0

# Cap concurrent Triton calls across all in-flight TTS chunks so a single
# large request (many chunks) cannot monopolise the connection pool.
_TTS_CHUNK_MAX_CONCURRENCY = 8
_tts_chunk_semaphore = asyncio.Semaphore(_TTS_CHUNK_MAX_CONCURRENCY)


class TTSTaskService(TextBase):
    """
    TaskService for Text-to-Speech inference, on the standard pipeline:

      preprocess_input    → sanitize (TextBase), then expand each input item
                            into ≤400-char chunk items carrying gender /
                            language_id (the adapter reads them per item);
                            per-item call mode = one Triton call per chunk
      run_inference       → parallel chunk dispatch via asyncio.gather
      convert_triton_output_to_task_format
                          → waveform extraction: FP32 tensor → int16 samples
                            (the mapper's to_output_items treats lists as
                            batch dims, which mangles waveform tensors)
      postprocess_output  → merge chunk samples back per input item, then
                            resample / duration-adjust / encode / base64
                            + response envelope
    """

    # One Triton call per (chunk) item — the TTS model takes one text per call.
    TRITON_CALL_MODE = "per_item"

    # ------------------------------------------------------------------
    # Preprocess — sanitize, then chunk expansion
    # ------------------------------------------------------------------

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = await super().preprocess_input(payload)
        config: Dict[str, Any] = payload.get("config") or {}
        gender = config.get("gender", "female")
        language_id = self._extract_source_lang(config.get("language") or {}) or ""

        chunked: List[Dict[str, Any]] = []
        for idx, item in enumerate(payload[self.payload_key]):
            duration = self._validated_duration(
                item.get("audioDuration") or item.get("audio_duration")
            )
            for piece in self._chunk_text(item.get("source", ""), _MAX_CHUNK_LENGTH):
                chunked.append({
                    "source": piece,
                    "gender": gender,
                    "language_id": language_id,
                    "_item_index": idx,        # merge key for postprocess
                    "audioDuration": duration,
                })
        payload[self.payload_key] = chunked
        return payload

    # ------------------------------------------------------------------
    # run_inference — parallel chunk dispatch
    # ------------------------------------------------------------------

    async def run_inference(
        self, payload: Dict[str, Any], serviceInfo: Dict[str, Any]
    ) -> Any:
        """Fan out all TTS chunks to Triton concurrently.

        The base class runs chunks sequentially (generic loop). TTS chunks are
        independent — no shared state between them — so they can all be
        in-flight simultaneously. Wall-clock latency drops from N×chunk_latency
        to max(chunk_latency), a ~5× improvement for a 2000-char input.
        """
        from trace.request_span import traced_inference
        from trace.phase_timer import timed_phase
        from trace.span_attributes import count_input_tokens, count_output_tokens, get_output_type
        from services.base.task_service import PostProcessFormat

        model_name = serviceInfo.get("name", "")
        triton_endpoint = serviceInfo.get("endpoint", "")
        api_key = serviceInfo.get("api_key")
        service_id = serviceInfo.get("serviceId", "")
        self._adapter_config = serviceInfo.get("adapter_config")

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                f"{self.task_name}: service_info is missing 'name' or 'endpoint'. "
                "Ensure the Orchestrator resolved the service before creating this task service."
            )

        input_items = payload.get(self.payload_key) or []
        config_data = payload.get("config", {})
        if not input_items:
            raise ValueError(f"{self.task_name}: input payload is empty or missing")

        source_texts = self.extract_field_from_items(input_items, "source")

        async def _run_chunk(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
            async with timed_phase("build_payload_ms"):
                triton_inputs, triton_outputs = await self.convert_payload_to_triton_format(
                    [chunk], config_data
                )
            async with traced_inference(payload, self.task_name, self.logger) as span_ctx:
                span_ctx["service_id"] = service_id
                with timed_phase("input_tokens_ms"):
                    span_ctx["input_tokens"] = count_input_tokens(
                        [chunk], span_ctx["input_type"]
                    )
                async with _tts_chunk_semaphore:
                    async with timed_phase("triton_ms"):
                        raw_triton_output = await self._call_triton_inference(
                            triton_endpoint=triton_endpoint,
                            triton_inputs=triton_inputs,
                            triton_outputs=triton_outputs,
                            api_key=api_key,
                        )
                async with timed_phase("output_convert_ms"):
                    chunk_results = await self.convert_triton_output_to_task_format(
                        raw_triton_output
                    )
                with timed_phase("output_tokens_ms"):
                    span_ctx["output_type"] = get_output_type(chunk_results)
                    span_ctx["output_tokens"] = count_output_tokens(
                        chunk_results, span_ctx["output_type"]
                    )
            return chunk_results

        results = await asyncio.gather(*[_run_chunk(c) for c in input_items])
        response_data = [item for chunk_result in results for item in chunk_result]

        return PostProcessFormat(
            payload=payload,
            response_data=response_data,
            source_texts=source_texts,
        )

    # ------------------------------------------------------------------
    # Output conversion — waveform tensors need raw extraction
    # ------------------------------------------------------------------

    async def convert_triton_output_to_task_format(
        self, triton_output: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Offload waveform conversion to a thread (np.array on a 66k-element list
        takes 5–20 ms and must not block the event loop)."""
        return await asyncio.to_thread(self._convert_audio_sync, triton_output)

    def _convert_audio_sync(self, triton_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract OUTPUT_GENERATED_AUDIO directly from the Triton response.

        The generic mapper path is unsuitable here: to_output_items treats a
        list value as a batch dimension and would explode a waveform of N
        samples into N one-float items. FP32 [-1, 1] → int16.
        """
        audio_data = None
        for output in triton_output.get("outputs", []):
            if output.get("name") == "OUTPUT_GENERATED_AUDIO":
                audio_data = output.get("data")
                break
        if audio_data is None:
            raise RuntimeError(
                f"{self.task_name}: OUTPUT_GENERATED_AUDIO not found in Triton response"
            )
        audio_fp32 = np.asarray(audio_data, dtype=np.float32).ravel()
        np.multiply(audio_fp32, np.float32(32767.0), out=audio_fp32)
        np.clip(audio_fp32, -32768, 32767, out=audio_fp32)
        audio_int16 = audio_fp32.astype(np.int16)
        return [{"samples": audio_int16}]

    # ------------------------------------------------------------------
    # postprocess_output — merge chunks per item, resample/encode + envelope
    # ------------------------------------------------------------------

    async def postprocess_output(self, result) -> Dict[str, Any]:
        payload = result.payload
        config: Dict[str, Any] = payload.get("config") or {}
        source_lang  = self._extract_source_lang(self._get_language(payload)) or ""
        target_rate  = self._validated_sample_rate(config)
        audio_format = (config.get("audioFormat") or config.get("audio_format") or "wav").lower()

        # Cheap: regroup chunk samples by originating input item (event loop).
        chunk_items = payload.get(self.payload_key) or []
        merged: Dict[int, List[np.ndarray]] = {}
        durations_req: Dict[int, Any] = {}
        for chunk, item in zip(chunk_items, result.response_data):
            idx = chunk.get("_item_index", 0)
            merged.setdefault(idx, []).append(item["samples"])
            durations_req[idx] = chunk.get("audioDuration")

        # Heavy: resample + encode per item — offload to thread pool so the
        # event loop is free during scipy FFT and pydub/ffmpeg export.
        processed = await asyncio.gather(*[
            asyncio.to_thread(
                self._process_merged_audio,
                merged[idx], durations_req.get(idx), target_rate, audio_format,
            )
            for idx in sorted(merged)
        ])

        audio_outputs = [p["audio_output"] for p in processed]
        durations     = [p["duration"]      for p in processed]

        return {
            "audio": audio_outputs,
            "config": {
                "language": {
                    "sourceLanguage":   source_lang,
                    "sourceScriptCode": None,
                },
                "audioFormat":   audio_format,
                "encoding":      "base64",
                "samplingRate":  target_rate,
                # Scalar field — accurate for single-item requests (the common
                # case); multi-item callers should read audio[i].audioDuration.
                "audioDuration": durations[0] if durations else 0,
            },
            "smr_response": None,
        }

    def _process_merged_audio(
        self,
        arrays: List[np.ndarray],
        audio_duration: Any,
        target_rate: int,
        audio_format: str,
    ) -> Dict[str, Any]:
        """Concatenate, resample, stretch/pad, and encode one output item.

        Runs in a thread-pool worker so scipy FFT resample and pydub/ffmpeg
        export do not block the event loop.
        """
        combined = np.concatenate(arrays) if len(arrays) > 1 else arrays[0]
        if target_rate != _TRITON_SAMPLE_RATE:
            combined = self._resample_audio(combined, _TRITON_SAMPLE_RATE, target_rate)
        if audio_duration is not None:
            actual = len(combined) / target_rate
            if actual > audio_duration:
                combined = self._stretch_audio(combined, target_rate, audio_duration)
            elif actual < audio_duration:
                combined = self._append_silence(combined, target_rate, audio_duration)
        duration = len(combined) / target_rate
        audio_bytes = self._to_audio_bytes(combined, target_rate, audio_format)
        return {
            "audio_output": {
                "audioContent": base64.b64encode(audio_bytes).decode("utf-8"),
                "audioUri": None,
                "audioDuration": duration,
            },
            "duration": duration,
        }

    # ------------------------------------------------------------------
    # Input bounds (user-controlled numerics)
    # ------------------------------------------------------------------

    def _validated_sample_rate(self, config: Dict[str, Any]) -> int:
        """Parse samplingRate, rejecting junk and out-of-range values with a 400."""
        raw = config.get("samplingRate") or config.get("sampling_rate") or _TRITON_SAMPLE_RATE
        try:
            rate = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{self.task_name}: samplingRate must be an integer, got {raw!r}") from exc
        if not _MIN_SAMPLE_RATE <= rate <= _MAX_SAMPLE_RATE:
            raise ValueError(
                f"{self.task_name}: samplingRate must be between "
                f"{_MIN_SAMPLE_RATE} and {_MAX_SAMPLE_RATE}, got {rate}"
            )
        return rate

    def _validated_duration(self, raw: Any) -> Any:
        """Parse audioDuration (None = keep natural length), bounded to prevent
        unbounded silence-padding allocations."""
        if raw is None:
            return None
        try:
            duration = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{self.task_name}: audioDuration must be a number, got {raw!r}") from exc
        if not 0 < duration <= _MAX_AUDIO_DURATION_S:
            raise ValueError(
                f"{self.task_name}: audioDuration must be between 0 and "
                f"{_MAX_AUDIO_DURATION_S} seconds, got {duration}"
            )
        return duration

    # ------------------------------------------------------------------
    # Text chunking
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str, max_length: int = 400) -> List[str]:
        """Split text into chunks ≤ max_length chars at sentence/clause boundaries."""
        text = self._normalize_text(text)
        if not text:
            return [""]
        if len(text) <= max_length:
            return [text]

        chunks: List[str] = []
        while len(text) > max_length:
            split_pos = max_length
            for sep in ('.', '?', '!', '।', ',', ' '):
                pos = text.rfind(sep, 0, max_length)
                if pos > 0:
                    split_pos = pos + 1
                    break
            chunks.append(text[:split_pos].strip())
            text = text[split_pos:].strip()

        if text:
            chunks.append(text)
        return [c for c in chunks if c]

    # ------------------------------------------------------------------
    # Audio processing helpers
    # ------------------------------------------------------------------

    def _resample_audio(self, audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
        if from_rate == to_rate:
            return audio
        # resample_poly (polyphase filter) is 3–10x faster than resample (full FFT)
        # for rational rate conversions — same approach as ASR preprocessing.
        g = gcd(int(from_rate), int(to_rate))
        resampled = sps.resample_poly(audio.astype(np.float32, copy=False), to_rate // g, from_rate // g)
        return np.clip(resampled, -32768, 32767).astype(np.int16)

    def _stretch_audio(self, audio: np.ndarray, sample_rate: int, target_duration: float) -> np.ndarray:
        """Speed-stretch audio to fit target_duration by resampling to target sample count."""
        target_samples = max(1, int(target_duration * sample_rate))
        g = gcd(target_samples, max(len(audio), 1))
        resampled = sps.resample_poly(audio.astype(np.float32, copy=False), target_samples // g, len(audio) // g)
        return np.clip(resampled, -32768, 32767).astype(np.int16)

    def _append_silence(self, audio: np.ndarray, sample_rate: int, target_duration: float) -> np.ndarray:
        """Pad audio with trailing silence to reach target_duration."""
        target_samples = int(target_duration * sample_rate)
        if target_samples <= len(audio):
            return audio
        padding = np.zeros(target_samples - len(audio), dtype=np.int16)
        return np.concatenate([audio, padding])

    def _to_audio_bytes(self, audio: np.ndarray, sample_rate: int, audio_format: str) -> bytes:
        """Convert int16 numpy array to bytes in the requested format."""
        wav_buffer = BytesIO()
        wav_io.write(wav_buffer, sample_rate, audio)
        wav_bytes = wav_buffer.getvalue()

        if audio_format == "wav":
            return wav_bytes
        try:
            segment = AudioSegment.from_wav(BytesIO(wav_bytes))
            out_buffer = BytesIO()
            segment.export(out_buffer, format=audio_format)
            return out_buffer.getvalue()
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"{self.task_name}: audio format '{audio_format}' requires ffmpeg — "
                "install ffmpeg or request audioFormat 'wav'"
            ) from exc
