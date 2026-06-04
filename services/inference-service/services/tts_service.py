"""TTS (Text-to-Speech) TaskService implementation."""

import base64
from io import BytesIO
from typing import Any, Dict, List

import numpy as np
import scipy.io.wavfile as wav_io
import scipy.signal as sps

from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
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


class TTSTaskService(TextBase):
    """
    TaskService for Text-to-Speech inference.

    Extends TextBase for text validation and normalization. Follows the
    standard pipeline with TTS-specific hook implementations:
      execute_triton_inference → per-item chunking (≤ 400 chars per Triton
                                 call), audio concatenation across chunks
      postprocess           → resample, duration-adjust, encode to
                                 audioFormat, base64 + response envelope
    """

    # ------------------------------------------------------------------
    # execute_triton_inference — chunked Triton loop (TTS call pattern)
    # ------------------------------------------------------------------

    async def execute_triton_inference(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        For each input item: normalize text → chunk (≤ 400 chars) → Triton
        call per chunk → concatenate FP32 arrays → int16.
        Returns one response item per input with the raw synthesized audio
        at _TRITON_SAMPLE_RATE; postprocess does the shaping.
        """
        from trace.request_span import traced_inference
        from trace.span_attributes import count_input_tokens

        async with traced_inference(payload, self.task_name, self.logger) as span_ctx:
            span_ctx["output_type"] = "audio"  # TTS output is audio, success or failure

            triton_endpoint = self.service_info.get("endpoint", "")
            api_key         = self.service_info.get("api_key")
            adapter_config  = self.service_info.get("adapter_config")

            if not triton_endpoint:
                raise RuntimeError(
                    f"{self.task_name}: service_info is missing 'endpoint'. "
                    "Ensure the Orchestrator resolved the service before creating this task service."
                )
            if not adapter_config:
                raise RuntimeError(
                    f"{self.task_name}: adapter_config missing from service_info. "
                    "Every TTS service must have an adapter_config seeded in mm_services."
                )

            input_items: List[Dict[str, Any]] = payload.get(self.payload_key) or []
            config: Dict[str, Any] = payload.get("config") or {}

            span_ctx["input_tokens"] = count_input_tokens(input_items, span_ctx["input_type"])

            # Use TextBase helpers for language extraction
            language    = self._get_language(payload)
            source_lang = self._extract_source_lang(language) or ""
            gender      = config.get("gender", "female")

            # Normalise config for GenericTritonMapper path resolution
            triton_config = {
                "language": {"source_language": source_lang},
                "gender": gender,
            }
            mapper = GenericTritonMapper(adapter_config)

            response_data: List[Dict[str, Any]] = []
            source_texts: List[str] = []

            for item in input_items:
                item_dict = item if isinstance(item, dict) else item.model_dump(by_alias=False)
                source_text    = item_dict.get("source", "")
                audio_duration = item_dict.get("audioDuration") or item_dict.get("audio_duration")

                chunks = self._chunk_text(source_text, _MAX_CHUNK_LENGTH)
                chunk_arrays: List[np.ndarray] = []

                for chunk in chunks:
                    chunk_item = {"source": chunk, "gender": gender, "language_id": source_lang}
                    triton_inputs, triton_outputs = mapper.compose_triton_kserve_v2_payload(
                        input_data=[chunk_item], config=triton_config
                    )
                    raw_output = await self._call_triton_inference(
                        triton_endpoint=triton_endpoint,
                        triton_inputs=triton_inputs,
                        triton_outputs=triton_outputs,
                        api_key=api_key,
                    )
                    chunk_arrays.append(self._extract_audio_array(raw_output))

                combined = np.concatenate(chunk_arrays) if len(chunk_arrays) > 1 else chunk_arrays[0]
                response_data.append({
                    "samples":       combined,           # int16 @ _TRITON_SAMPLE_RATE
                    "audioDuration": audio_duration,     # requested duration, None = as-is
                })
                source_texts.append(source_text)

            span_ctx["output_tokens"] = len(response_data)

            return {
                "response_data": response_data,
                "source_texts": source_texts,
                "service_id": self.service_info.get("service_id", ""),
            }

    # ------------------------------------------------------------------
    # postprocess — resample / duration-adjust / encode + envelope
    # ------------------------------------------------------------------

    async def postprocess(
        self,
        payload: Dict[str, Any],
        response_items: List[Dict[str, Any]],
        source_texts: List[str],
    ) -> Dict[str, Any]:
        config: Dict[str, Any] = payload.get("config") or {}
        source_lang  = self._extract_source_lang(self._get_language(payload)) or ""
        target_rate  = self._validated_sample_rate(config)
        audio_format = (config.get("audioFormat") or config.get("audio_format") or "wav").lower()

        audio_outputs: List[Dict[str, Any]] = []
        durations: List[float] = []

        for item in response_items:
            combined = item["samples"]
            audio_duration = self._validated_duration(item.get("audioDuration"))

            # Resample to requested rate
            if target_rate != _TRITON_SAMPLE_RATE:
                combined = self._resample_audio(combined, _TRITON_SAMPLE_RATE, target_rate)

            # Duration adjustment
            if audio_duration is not None:
                actual_duration = len(combined) / target_rate
                if actual_duration > audio_duration:
                    combined = self._stretch_audio(combined, target_rate, audio_duration)
                elif actual_duration < audio_duration:
                    combined = self._append_silence(combined, target_rate, audio_duration)

            duration = len(combined) / target_rate
            durations.append(duration)

            # Format conversion + base64
            audio_bytes = self._to_audio_bytes(combined, target_rate, audio_format)
            audio_outputs.append({
                "audioContent": base64.b64encode(audio_bytes).decode("utf-8"),
                "audioUri": None,
                "audioDuration": duration,
            })

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

    def _extract_audio_array(self, triton_output: Dict[str, Any]) -> np.ndarray:
        """
        Extract OUTPUT_GENERATED_AUDIO from Triton response.
        Triton returns FP32 data; converts to int16 for downstream processing.
        """
        audio_data = None
        for output in triton_output.get("outputs", []):
            if output.get("name") == "OUTPUT_GENERATED_AUDIO":
                audio_data = output.get("data")
                break

        if audio_data is None:
            raise ValueError(
                f"{self.task_name}: OUTPUT_GENERATED_AUDIO not found in Triton response"
            )

        audio_fp32 = np.array(audio_data, dtype=np.float32).flatten()
        # FP32 range assumed [-1, 1] from Triton TTS model
        audio_int16 = np.clip(audio_fp32 * 32767, -32768, 32767).astype(np.int16)
        return audio_int16

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
        num_samples = round(len(audio) * float(to_rate) / from_rate)
        resampled = sps.resample(audio.astype(np.float32), num_samples)
        return np.clip(resampled, -32768, 32767).astype(np.int16)

    def _stretch_audio(self, audio: np.ndarray, sample_rate: int, target_duration: float) -> np.ndarray:
        """Speed-stretch audio to fit target_duration by resampling to target sample count."""
        target_samples = max(1, int(target_duration * sample_rate))
        resampled = sps.resample(audio.astype(np.float32), target_samples)
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
        segment = AudioSegment.from_wav(BytesIO(wav_bytes))
        out_buffer = BytesIO()
        segment.export(out_buffer, format=audio_format)
        return out_buffer.getvalue()
