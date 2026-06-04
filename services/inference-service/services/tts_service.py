"""TTS (Text-to-Speech) TaskService implementation."""

import base64
from io import BytesIO
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


class TTSTaskService(TextBase):
    """
    TaskService for Text-to-Speech inference, on the standard pipeline:

      preprocess_input    → sanitize (TextBase), then expand each input item
                            into ≤400-char chunk items carrying gender /
                            language_id (the adapter reads them per item);
                            per-item call mode = one Triton call per chunk
      run_inference       → generic (BaseTaskService) — no override
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
    # Output conversion — waveform tensors need raw extraction
    # ------------------------------------------------------------------

    async def convert_triton_output_to_task_format(
        self, triton_output: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract OUTPUT_GENERATED_AUDIO directly from the Triton response.

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
            raise ValueError(
                f"{self.task_name}: OUTPUT_GENERATED_AUDIO not found in Triton response"
            )

        audio_fp32 = np.array(audio_data, dtype=np.float32).flatten()
        audio_int16 = np.clip(audio_fp32 * 32767, -32768, 32767).astype(np.int16)
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

        # Chunk items (in payload) and chunk results (response_data) are
        # parallel — regroup samples by the originating input item.
        chunk_items = payload.get(self.payload_key) or []
        merged: Dict[int, List[np.ndarray]] = {}
        durations_req: Dict[int, Any] = {}
        for chunk, item in zip(chunk_items, result.response_data):
            idx = chunk.get("_item_index", 0)
            merged.setdefault(idx, []).append(item["samples"])
            durations_req[idx] = chunk.get("audioDuration")

        audio_outputs: List[Dict[str, Any]] = []
        durations: List[float] = []
        for idx in sorted(merged):
            arrays = merged[idx]
            combined = np.concatenate(arrays) if len(arrays) > 1 else arrays[0]

            if target_rate != _TRITON_SAMPLE_RATE:
                combined = self._resample_audio(combined, _TRITON_SAMPLE_RATE, target_rate)

            audio_duration = durations_req.get(idx)
            if audio_duration is not None:
                actual = len(combined) / target_rate
                if actual > audio_duration:
                    combined = self._stretch_audio(combined, target_rate, audio_duration)
                elif actual < audio_duration:
                    combined = self._append_silence(combined, target_rate, audio_duration)

            duration = len(combined) / target_rate
            durations.append(duration)
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
