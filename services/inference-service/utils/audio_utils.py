"""Stateless audio DSP helpers shared across audio-backed task services.

Pure functions over numpy arrays, no task state. ASR, TTS, and future audio
services compose these instead of re-implementing decode, resample, and
encode. Task-coupled IO (URI download with the SSRF guard, base64 resolution)
stays on the services; only the DSP primitives live here.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np
import scipy.io.wavfile as wav_io
import scipy.signal as sps
from pydub import AudioSegment


def decode_audio_bytes(audio_bytes: bytes) -> tuple[np.ndarray, int]:
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
