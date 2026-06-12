"""TTS (Text-to-Speech) TaskService implementation."""

import base64
from typing import Any, Dict, List

import numpy as np

from services.base.text_base import TextBase
from services.base.task_service import InferenceContext
from utils import audio_utils, text_utils

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
    TaskService for Text-to-Speech inference, on the standard pipeline:

      preprocess_input    → sanitize (TextBase), then expand each input item
                            into ≤400-char chunk items carrying gender /
                            language_id (the adapter reads them per item);
                            per-item call mode = one Triton call per chunk
      run_inference       → generic (BaseTaskService) — no override
      produce_result      → extract each chunk's waveform (FP32 → int16) from
                            the raw Triton responses, merge per input item, then
                            resample / duration-adjust / encode / base64
      build_envelope      → wrap the audio items + config echo

    TTS is a code-output service (no output_transform): the waveform DSP cannot
    be expressed as a JSON transform, so produce_result reads the raw tensors.
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
            duration = self._validated_duration(item.get("audioDuration"))
            for piece in text_utils.chunk_text(item.get("source", ""), _MAX_CHUNK_LENGTH):
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
    # Output conversion — waveform tensors need raw extraction
    # ------------------------------------------------------------------

    def _extract_waveform(self, triton_output: Dict[str, Any]) -> np.ndarray:
        """Extract OUTPUT_GENERATED_AUDIO (FP32 [-1, 1]) from a Triton response
        as int16 samples. The generic mapper path is unsuitable: it would
        explode an N-sample waveform into N one-float items."""
        audio_data = None
        for output in triton_output.get("outputs", []):
            if output.get("name") == "OUTPUT_GENERATED_AUDIO":
                audio_data = output.get("data")
                break
        if audio_data is None:
            raise RuntimeError(
                f"{self.task_name}: OUTPUT_GENERATED_AUDIO not found in Triton response"
            )
        audio_fp32 = np.array(audio_data, dtype=np.float32).flatten()
        return audio_utils.to_int16(audio_fp32 * 32767)

    # ------------------------------------------------------------------
    # produce_result — merge chunks per item, resample/encode the waveforms
    # build_envelope — wrap the audio items + config echo
    # ------------------------------------------------------------------

    async def produce_result(self, result: InferenceContext) -> InferenceContext:
        payload = result.payload
        config: Dict[str, Any] = payload.get("config") or {}
        target_rate  = self._validated_sample_rate(config)
        audio_format = (config.get("audioFormat") or "wav").lower()

        # Per-chunk int16 waveforms, parallel to chunk_items, extracted from the
        # raw Triton responses captured in run_inference.
        chunk_items = payload.get(self.payload_key) or []
        chunk_samples = [self._extract_waveform(raw) for raw in result.raw_triton_outputs]

        merged: Dict[int, List[np.ndarray]] = {}
        durations_req: Dict[int, Any] = {}
        for chunk, samples in zip(chunk_items, chunk_samples):
            idx = chunk.get("_item_index", 0)
            merged.setdefault(idx, []).append(samples)
            durations_req[idx] = chunk.get("audioDuration")

        audio_outputs: List[Dict[str, Any]] = []
        for idx in sorted(merged):
            arrays = merged[idx]
            combined = np.concatenate(arrays) if len(arrays) > 1 else arrays[0]

            if target_rate != _TRITON_SAMPLE_RATE:
                combined = audio_utils.to_int16(
                    audio_utils.resample(combined, _TRITON_SAMPLE_RATE, target_rate)
                )

            audio_duration = durations_req.get(idx)
            if audio_duration is not None:
                actual = len(combined) / target_rate
                if actual > audio_duration:
                    target_samples = max(1, int(audio_duration * target_rate))
                    combined = audio_utils.to_int16(
                        audio_utils.resample_to_count(combined, target_samples)
                    )
                elif actual < audio_duration:
                    combined = audio_utils.append_silence(combined, target_rate, audio_duration)

            duration = len(combined) / target_rate
            audio_bytes = audio_utils.encode_audio(combined, target_rate, audio_format)
            audio_outputs.append({
                "audioContent": base64.b64encode(audio_bytes).decode("utf-8"),
                "audioUri": None,
                "audioDuration": duration,
            })

        result.result_items = audio_outputs
        return result

    def build_envelope(self, result: InferenceContext) -> Dict[str, Any]:
        payload = result.payload
        config: Dict[str, Any] = payload.get("config") or {}
        source_lang  = self._extract_source_lang(self._get_language(payload)) or ""
        target_rate  = self._validated_sample_rate(config)
        audio_format = (config.get("audioFormat") or "wav").lower()
        items = result.result_items
        return {
            "audio": items,
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
                "audioDuration": items[0]["audioDuration"] if items else 0,
            },
        }

    # ------------------------------------------------------------------
    # Input bounds (user-controlled numerics)
    # ------------------------------------------------------------------

    def _validated_sample_rate(self, config: Dict[str, Any]) -> int:
        """Parse samplingRate, rejecting junk and out-of-range values with a 400."""
        raw = config.get("samplingRate") or _TRITON_SAMPLE_RATE
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
