"""
Audio processing service with utilities for audio manipulation.

Ported from Dhruva-Platform-2 audio_service.py for ASR processing.
"""

import asyncio
import logging
from io import BytesIO
from typing import List, Dict, Tuple, Optional
import numpy as np
import scipy.signal as sps
from pydub import AudioSegment
from pydub.effects import normalize as pydub_normalize
import torch
try:
    from torchaudio.io import AudioEffector
    AUDIO_EFFECTOR_AVAILABLE = True
except ImportError:
    AUDIO_EFFECTOR_AVAILABLE = False
import httpx
import soundfile as sf

logger = logging.getLogger(__name__)


class AudioService:
    """Audio processing service for ASR operations."""
    
    def __init__(self):
        """Initialize audio service."""
        pass
    
    def stereo_to_mono(self, audio: np.ndarray) -> np.ndarray:
        """Convert stereo audio to mono by averaging channels."""
        if len(audio.shape) > 1:
            # Average channels: (left + right) / 2
            return audio.sum(axis=1) / 2
        return audio
    
    def resample_audio(self, audio: np.ndarray, sampling_rate: int, target_rate: int) -> np.ndarray:
        """Resample audio to target sample rate."""
        if sampling_rate == target_rate:
            return audio
        
        # Calculate number of samples for target rate
        number_of_samples = round(len(audio) * float(target_rate) / sampling_rate)
        
        # Use scipy.signal.resample
        resampled = sps.resample(audio, number_of_samples)
        
        return resampled
    
    def equalize_amplitude(self, audio: np.ndarray, frame_rate: int) -> AudioSegment:
        """Equalize audio amplitude using pydub normalization."""
        # Quantize to int16 range
        audio_quantized = audio * (2**15 - 1)
        
        # Convert to int16
        audio_int16 = audio_quantized.astype(np.int16)
        
        # Create AudioSegment from numpy array
        audio_segment = AudioSegment(
            audio_int16.tobytes(),
            frame_rate=frame_rate,
            sample_width=2,  # 16-bit
            channels=1
        )
        
        # Normalize using pydub
        normalized = pydub_normalize(audio_segment)
        
        return normalized
    
    def dequantize_audio(self, audio: AudioSegment) -> np.ndarray:
        """Convert AudioSegment back to float64 numpy array."""
        # Get array of samples
        samples = audio.get_array_of_samples()
        
        # Convert to float64 and normalize
        audio_float = np.array(samples).astype('float64') / (2**15 - 1)
        
        return audio_float
    
    async def silero_vad_chunking(
        self,
        audio: np.ndarray,
        sample_rate: int,
        max_chunk_duration_s: float = 7.0,
        min_speech_duration_ms: int = 100,
        triton_client=None
    ) -> Tuple[List[np.ndarray], List[Dict[str, float]]]:
        """
        Perform VAD chunking using Silero VAD model via Triton.
        
        Note: This requires TritonClient dependency injection.
        """
        if not triton_client:
            logger.warning("TritonClient not available, skipping VAD chunking")
            return [audio], [{"start": 0, "end": len(audio), "start_secs": 0, "end_secs": len(audio) / sample_rate}]
        
        try:
            # Prepare VAD inputs for Triton
            vad_inputs, vad_outputs = triton_client.get_vad_io_for_triton(
                audio=audio,
                sample_rate=sample_rate,
                threshold=0.3,
                min_silence_duration_ms=400,
                speech_pad_ms=200,
                min_speech_duration_ms=min_speech_duration_ms
            )
            
            # Send VAD request to Triton
            vad_response = triton_client.send_triton_request("vad", vad_inputs, vad_outputs)
            
            # Extract speech timestamps
            speech_timestamps = vad_response.as_numpy("TIMESTAMPS")
            
            # Adjust timestamps
            adjusted_timestamps = self.adjust_timestamps(
                speech_timestamps, sample_rate, max_chunk_duration_s
            )
            
            # Split audio into chunks
            audio_chunks = []
            for timestamp in adjusted_timestamps:
                start_sample = int(timestamp["start"])
                end_sample = int(timestamp["end"])
                chunk = audio[start_sample:end_sample]
                audio_chunks.append(chunk)
            
            return audio_chunks, adjusted_timestamps
            
        except Exception as e:
            logger.error(f"VAD chunking failed: {e}")
            # Fallback to single chunk
            return [audio], [{"start": 0, "end": len(audio), "start_secs": 0, "end_secs": len(audio) / sample_rate}]
    
    def adjust_timestamps(
        self,
        speech_timestamps: List[Dict[str, float]],
        sample_rate: int,
        max_chunk_duration_s: float
    ) -> List[Dict[str, float]]:
        """Adjust speech timestamps for optimal chunking."""
        if not speech_timestamps:
            return []
        
        adjusted_timestamps = []
        max_chunk_duration_samples = int(max_chunk_duration_s * sample_rate)
        
        for i, timestamp in enumerate(speech_timestamps):
            start = timestamp["start"]
            end = timestamp["end"]
            start_secs = start / sample_rate
            end_secs = end / sample_rate
            
            # Check if we can merge with previous chunk
            if (adjusted_timestamps and 
                start - adjusted_timestamps[-1]["end"] < 3 * sample_rate and  # Gap < 3 seconds
                end - adjusted_timestamps[-1]["start"] <= max_chunk_duration_samples):  # Total duration <= max
                
                # Merge with previous chunk
                adjusted_timestamps[-1]["end"] = end
                adjusted_timestamps[-1]["end_secs"] = end_secs
            else:
                # Check if chunk is too long
                if end - start > max_chunk_duration_samples:
                    # Split into smaller chunks
                    chunks = self._windowed_chunking(
                        start, start_secs, end - start, max_chunk_duration_s, sample_rate
                    )
                    adjusted_timestamps.extend(chunks)
                else:
                    # Add as-is
                    adjusted_timestamps.append({
                        "start": start,
                        "end": end,
                        "start_secs": start_secs,
                        "end_secs": end_secs
                    })
        
        return adjusted_timestamps
    
    def _windowed_chunking(
        self,
        curr_start: float,
        curr_start_secs: float,
        chunk_duration: float,
        max_chunk_duration_s: float,
        sample_rate: int
    ) -> List[Dict[str, float]]:
        """Split long chunk into smaller windows."""
        chunks = []
        max_chunk_samples = int(max_chunk_duration_s * sample_rate)
        
        start = curr_start
        start_secs = curr_start_secs
        
        while start < curr_start + chunk_duration:
            end = min(start + max_chunk_samples, curr_start + chunk_duration)
            end_secs = end / sample_rate
            
            chunks.append({
                "start": start,
                "end": end,
                "start_secs": start_secs,
                "end_secs": end_secs
            })
            
            start = end
            start_secs = end_secs
        
        # Merge last small chunk if it's too small
        if len(chunks) > 1 and chunks[-1]["end"] - chunks[-1]["start"] < 3 * sample_rate:
            chunks[-2]["end"] = chunks[-1]["end"]
            chunks[-2]["end_secs"] = chunks[-1]["end_secs"]
            chunks.pop()
        
        return chunks
    
    async def download_audio(self, url: str) -> bytes:
        """Download audio from URL."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"Failed to download audio from {url}: {e}")
            raise
    
    def stretch_audio(self, input_audio: np.ndarray, speed_factor: float, sample_rate: int) -> np.ndarray:
        """Stretch audio by speed factor using torchaudio."""
        try:
            if AUDIO_EFFECTOR_AVAILABLE:
                # Convert to tensor
                audio_tensor = torch.from_numpy(input_audio).unsqueeze(0)
                
                # Create AudioEffector with atempo effect
                effector = AudioEffector(effects=[f"atempo={speed_factor}"])
                
                # Apply effect
                stretched = effector.apply(audio_tensor, sample_rate)
                
                # Convert back to numpy
                return stretched.squeeze(0).numpy()
            else:
                # Fallback: simple time stretching using scipy
                logger.warning("AudioEffector not available, using fallback method")
                from scipy.interpolate import interp1d
                
                # Calculate new length
                new_length = int(len(input_audio) / speed_factor)
                
                # Create time indices
                old_indices = np.linspace(0, len(input_audio) - 1, len(input_audio))
                new_indices = np.linspace(0, len(input_audio) - 1, new_length)
                
                # Interpolate
                f = interp1d(old_indices, input_audio, kind='linear', bounds_error=False, fill_value=0)
                return f(new_indices)
            
        except Exception as e:
            logger.error(f"Audio stretching failed: {e}")
            return input_audio
    
    def append_silence(
        self,
        input_audio: np.ndarray,
        silence_duration: float,
        sample_rate: int
    ) -> np.ndarray:
        """Append silence to audio."""
        try:
            # Create silence segment
            silence_samples = int(silence_duration * sample_rate)
            silence = np.zeros(silence_samples, dtype=input_audio.dtype)
            
            # Concatenate
            return np.concatenate([input_audio, silence])
            
        except Exception as e:
            logger.error(f"Silence appending failed: {e}")
            return input_audio
