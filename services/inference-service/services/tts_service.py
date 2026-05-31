"""TTS (Text-to-Speech) TaskService implementation."""

import base64
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional

import numpy as np
import scipy.io.wavfile as wav_io
import scipy.signal as sps

from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Triton model always outputs at this rate
_TRITON_SAMPLE_RATE = 22050
# Maximum characters per Triton call
_MAX_CHUNK_LENGTH = 400


class TTSTaskService(TextBase):
    """
    TaskService for Text-to-Speech inference.

    Extends TextBase for text validation and normalization.
    Overrides run_inference to handle:
      - per-item character-level chunking (≤ 400 chars per Triton call)
      - audio concatenation across chunks
      - resampling, duration adjustment, format conversion, base64 encoding
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    # ------------------------------------------------------------------
    # Inference — full TTS pipeline
    # ------------------------------------------------------------------

    async def run_inference(self, payload: Dict[str, Any], **_: Any) -> Any:
        """
        TTS pipeline:
          for each input item:
            normalize text → chunk (≤ 400 chars) → Triton call per chunk
            → concatenate FP32 arrays → int16 → resample → duration-adjust
            → encode to audioFormat → base64
        """
        import time
        from trace.request_span import tracer, compute_total_time_ms, log_span_attributes
        from trace.span_attributes import get_input_type, count_input_tokens

        start_time = time.time()

        # ai-inference span mirrors the text/image base (task_service.py) and the
        # audio base. TTS overrides run_inference with its own Triton loop, so the
        # span must be opened here too — otherwise TTS traces lack ai-inference.
        with tracer.start_as_current_span("ai-inference") as inference_span:
            try:
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

                input_items: List[Dict[str, Any]] = payload.get("input", [])
                config: Dict[str, Any] = payload.get("config") or {}

                # Compute input metrics for ai-inference span (TTS input is text)
                input_type = get_input_type(payload)
                input_tokens = count_input_tokens(input_items, input_type)

                # Use TextBase helpers for language extraction
                language     = self._get_language(payload)
                source_lang  = self._extract_source_lang(language) or ""
                gender       = config.get("gender", "female")
                target_rate  = int(config.get("samplingRate") or config.get("sampling_rate") or _TRITON_SAMPLE_RATE)
                audio_format = (config.get("audioFormat") or config.get("audio_format") or "wav").lower()

                # Normalise config for GenericTritonMapper path resolution
                triton_config = {
                    "language": {"source_language": source_lang},
                    "gender": gender,
                }

                audio_outputs: List[Dict[str, Any]] = []

                for item in input_items:
                    item_dict = item if isinstance(item, dict) else item.model_dump(by_alias=False)
                    source_text    = item_dict.get("source", "")
                    audio_duration = item_dict.get("audioDuration") or item_dict.get("audio_duration")

                    chunks = self._chunk_text(source_text, _MAX_CHUNK_LENGTH)
                    chunk_arrays: List[np.ndarray] = []

                    for chunk in chunks:
                        chunk_item = {"source": chunk, "gender": gender, "language_id": source_lang}
                        triton_inputs, triton_outputs = self._build_triton_inputs(
                            adapter_config, [chunk_item], triton_config
                        )
                        raw_output = await self._call_triton_inference(
                            triton_endpoint=triton_endpoint,
                            triton_inputs=triton_inputs,
                            triton_outputs=triton_outputs,
                            api_key=api_key,
                        )
                        audio_array = self._extract_audio_array(raw_output)
                        chunk_arrays.append(audio_array)

                    # Assemble chunks
                    combined = np.concatenate(chunk_arrays) if len(chunk_arrays) > 1 else chunk_arrays[0]

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

                    actual_duration = len(combined) / target_rate

                    # Format conversion + base64
                    audio_bytes = self._to_audio_bytes(combined, target_rate, audio_format)
                    audio_b64   = base64.b64encode(audio_bytes).decode("utf-8")

                    audio_outputs.append({
                        "audioContent":   audio_b64,
                        "_audioDuration": actual_duration,
                    })

                postprocessed = {
                    "audio":  [{"audioContent": o["audioContent"], "audioUri": None} for o in audio_outputs],
                    "config": {
                        "language": {
                            "sourceLanguage":    source_lang,
                            "sourceScriptCode":  None,
                        },
                        "audioFormat":   audio_format,
                        "encoding":      "base64",
                        "samplingRate":  target_rate,
                        "audioDuration": audio_outputs[0]["_audioDuration"] if audio_outputs else 0,
                    },
                    "smr_response": None,
                }
                response = self._build_response(payload, postprocessed)

                # Set ai-inference span attributes (TTS output is audio)
                span_attrs = {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "input_tokens": input_tokens,
                    "output_tokens": len(audio_outputs),
                    "input_type": input_type,
                    "output_type": "audio",
                    "status": "success",
                    "status_code": 200,
                }
                for k, v in span_attrs.items():
                    inference_span.set_attribute(k, v)
                log_span_attributes("ai-inference", inference_span, span_attrs)

                return response
            except Exception as e:
                self.logger.error(f"{self.task_name}: TTS inference failed: {e}", exc_info=True)
                # Set error status on span
                span_attrs = {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "input_type": get_input_type(payload),
                    "output_type": "audio",
                    "status": "failure",
                    "status_code": 500,
                }
                for k, v in span_attrs.items():
                    inference_span.set_attribute(k, v)
                log_span_attributes("ai-inference", inference_span, span_attrs)
                raise

    # ------------------------------------------------------------------
    # Triton helpers
    # ------------------------------------------------------------------

    def _build_triton_inputs(
        self,
        adapter_config: Any,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ):
        """Build KServe v2 payload from adapter_config."""
        mapper = GenericTritonMapper(adapter_config)
        return mapper.compose_triton_kserve_v2_payload(input_data=input_data, config=config)

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

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        # Not used — run_inference builds the response directly
        return {"audio": response_items}

    def _build_response(self, payload: Dict[str, Any], postprocessed: Dict[str, Any]) -> Dict[str, Any]:
        return postprocessed
