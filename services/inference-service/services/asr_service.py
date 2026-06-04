"""ASR TaskService — Automatic Speech Recognition inference."""

import base64
from io import BytesIO
from typing import Any, Dict, List, Tuple

import numpy as np
import scipy.signal as sps

from services.base.audio_base import AudioBase
from services.base.task_service import PostProcessFormat


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
            audio_data, sample_rate = await self._decode_audio_bytes(audio_bytes)
            audio_data              = self._stereo_to_mono(audio_data)
            audio_data              = self._resample(audio_data, sample_rate, self.TARGET_SAMPLE_RATE)
            audio_data              = self._equalize_amplitude(audio_data)

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

    async def _decode_audio_bytes(self, audio_bytes: bytes) -> Tuple[Any, int]:
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
            self.logger.warning(
                "soundfile failed to decode audio (%s), falling back to raw PCM", sf_err
            )
            # Fallback: treat raw bytes as little-endian int16 PCM at 16kHz
            try:
                audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                return audio_data, 16000
            except Exception as pcm_err:
                self.logger.error("Failed to decode audio: %s", pcm_err)
                raise RuntimeError(
                    f"{self.task_name}: unable to decode audio bytes"
                ) from pcm_err

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

    def _equalize_amplitude(self, audio: Any) -> Any:
        """
        Normalize audio amplitude to the [-1, 1] range.
        Returns normalized float32 numpy array.
        """
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val
        return audio.astype(np.float32)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    async def postprocess_output(self, result: PostProcessFormat) -> Dict[str, Any]:
        """Decode bytes → wrap in TranscriptionOutput list.

        result.source_texts (the audio URIs collected by AudioBase) is
        intentionally unused: per the ULCA ASR contract, output[].source
        carries the transcript itself. Transcripts map to audio items by index.
        """
        decoded = await self._decode_output_bytes(result.response_data)
        return self._wrap_transcription_output(decoded)

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
        """
        decoded = []
        for item in response_items:
            d = dict(item) if isinstance(item, dict) else {}
            for key, value in d.items():
                if isinstance(value, (bytes, np.ndarray)):
                    d[key] = await self._decode_transcript(value)
            decoded.append(d)
        return decoded

    def _wrap_transcription_output(
        self, decoded_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Wrap decoded transcript strings in TranscriptionOutput dicts.
        Returns {"output": [{"source": <transcript>, "nBestTokens": ...}, ...]} —
        ULCA ASR contract: output[].source is the transcript.
        """
        output = []
        for item in decoded_items:
            transcript = item.get("transcript", item.get("source", ""))
            n_best = item.get("nBestTokens", item.get("n_best_tokens"))
            output.append({"source": str(transcript), "nBestTokens": n_best})
        return {"output": output}
