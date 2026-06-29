"""
AudioBase — base class for all audio-backed inference services.

Covers: ASR, Audio Language Detection, Language Diarization, Speaker Diarization.

Inherits the BaseTaskService pipeline and sets:
  REQUIRED_ITEM_FIELDS → each item needs audioContent or audioUri
  preprocess_input      → base64 passthrough (downloads audioUri if needed)
  TRITON_CALL_MODE      → 'per_item': one Triton call per audio item

adapter_config value_paths read the item directly (input.audioContent), so no
context-builder hook is needed. The passthrough default fits tasks where Triton
decodes audio internally (ALD, Speaker Diarization, Language Diarization). ASR
is the exception: it needs float-PCM preprocessing and overrides preprocess_input
(reusing _get_audio_bytes here), writing input.samples for its config to read.

Request keys are camelCase (ULCA): audioContent, audioUri.
"""

import base64
from io import BytesIO
from typing import Any, Dict, Optional

import httpx
import numpy as np
import scipy.io.wavfile as wav_io
import scipy.signal as sps
from pydub import AudioSegment

from services.base.task_service import BaseTaskService


# ----------------------------------------------------------------------------
# Stateless audio DSP helpers (decode, resample, encode).
#
# Pure functions over numpy arrays, no task state. ASR and TTS compose these
# instead of re-implementing them. Module-level (not AudioBase methods) so TTS
# — a TextBase service, not an AudioBase one — can reuse them without an
# AudioBase instance. Task-coupled IO (URI download, base64 resolution) stays
# on the service classes; only the DSP primitives live here.
# ----------------------------------------------------------------------------

def decode_audio_bytes(audio_bytes: bytes) -> tuple:
    """Decode raw audio bytes to (float32 samples, sample_rate).

    Raises ValueError on undecodable input. Reinterpreting undecodable bytes
    as raw PCM produced valid-looking noise that transcribed to garbage, so
    decode failure is surfaced, not swallowed.
    """
    import soundfile as sf

    try:
        audio_data, sample_rate = sf.read(
            BytesIO(audio_bytes), dtype="float32", always_2d=False
        )
        return audio_data, sample_rate
    except Exception as sf_err:
        raise ValueError(
            f"unable to decode audio (expected a valid wav/flac/ogg stream): {sf_err}"
        ) from sf_err


def stereo_to_mono(audio: np.ndarray) -> np.ndarray:
    """Average channels to mono. No-op if already mono."""
    if isinstance(audio, np.ndarray) and audio.ndim > 1:
        return audio.mean(axis=1).astype(np.float32)
    return audio


def resample(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """Resample a float array from from_rate to to_rate. No-op if equal."""
    if from_rate == to_rate:
        return audio
    num_samples = round(len(audio) * float(to_rate) / from_rate)
    resampled = sps.resample(audio.astype(np.float32), num_samples)
    return resampled.astype(np.float32)


def resample_to_count(audio: np.ndarray, num_samples: int) -> np.ndarray:
    """Resample a float array to an explicit sample count (time stretch)."""
    resampled = sps.resample(audio.astype(np.float32), num_samples)
    return resampled.astype(np.float32)


def equalize_amplitude(audio: np.ndarray) -> np.ndarray:
    """Normalise amplitude to the [-1, 1] range. No-op on silence."""
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val
    return audio.astype(np.float32)


def to_int16(audio: np.ndarray) -> np.ndarray:
    """Clip to the int16 range and cast. Caller scales floats first."""
    return np.clip(audio, -32768, 32767).astype(np.int16)


def append_silence(
    audio: np.ndarray, sample_rate: int, target_duration: float
) -> np.ndarray:
    """Pad with trailing silence to reach target_duration. No-op if longer."""
    target_samples = int(target_duration * sample_rate)
    if target_samples <= len(audio):
        return audio
    padding = np.zeros(target_samples - len(audio), dtype=np.int16)
    return np.concatenate([audio, padding])


def encode_audio(audio: np.ndarray, sample_rate: int, audio_format: str) -> bytes:
    """Encode an int16 sample array to bytes in the requested format.

    wav is written directly; other formats round-trip through pydub.
    """
    wav_buffer = BytesIO()
    wav_io.write(wav_buffer, sample_rate, audio)
    wav_bytes = wav_buffer.getvalue()

    if audio_format == "wav":
        return wav_bytes
    segment = AudioSegment.from_wav(BytesIO(wav_bytes))
    out_buffer = BytesIO()
    segment.export(out_buffer, format=audio_format)
    return out_buffer.getvalue()


class AudioBase(BaseTaskService):
    """Base class for all audio inference services."""

    payload_key = "audio"  # audio input list lives under payload['audio']

    # Audio Triton models accept one file per request — run_inference loops
    # per item instead of one batch call.
    TRITON_CALL_MODE = "per_item"

    # Each audio item must carry inline content or a URI to download.
    REQUIRED_ITEM_FIELDS = (("audioContent", "audioUri"),)

    # ------------------------------------------------------------------
    # Preprocessing — base64 passthrough (default)
    # ------------------------------------------------------------------

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Pass each item through as-is. If only audioUri is provided, download
        and base64-encode it so the renderer always has audioContent.
        ASR overrides this with its float-PCM pipeline."""
        items = []
        for item in payload.get(self.payload_key) or []:
            d = item
            if not d.get("audioContent") and d.get("audioUri"):
                d = dict(d)
                d["audioContent"] = base64.b64encode(
                    await self._download_audio(str(d["audioUri"]))
                ).decode("utf-8")
            items.append(d)
        payload[self.payload_key] = items
        return payload

    # ------------------------------------------------------------------
    # Audio input helpers
    # ------------------------------------------------------------------

    async def _get_audio_bytes(self, audio_input: Dict[str, Any]) -> bytes:
        """Return raw audio bytes: base64-decode audioContent or download
        audioUri. Used by ASR's float-PCM preprocessing."""
        if audio_input.get("audioContent"):
            return base64.b64decode(audio_input["audioContent"])
        if audio_input.get("audioUri"):
            return await self._download_audio(str(audio_input["audioUri"]))
        raise ValueError(
            f"{self.task_name}: audio item must have audioContent or audioUri"
        )

    async def _download_audio(self, uri: str) -> bytes:
        """Download raw audio bytes from an HTTP/HTTPS URI.
        The URI is user-supplied — validated against the SSRF guard first."""
        self._validate_external_url(uri)
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
