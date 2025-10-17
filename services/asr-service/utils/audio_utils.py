"""
Audio utility functions for validation and format conversion.
"""

import logging
from io import BytesIO
from typing import Optional
import soundfile as sf
from pydub import AudioSegment

logger = logging.getLogger(__name__)


class InvalidAudioFormatError(Exception):
    """Custom exception for invalid audio format errors."""
    pass


class InvalidSampleRateError(Exception):
    """Custom exception for invalid sample rate errors."""
    pass


class AudioProcessingError(Exception):
    """Custom exception for audio processing errors."""
    pass


def validate_audio_format(audio_bytes: bytes) -> str:
    """Validate audio format by checking magic bytes."""
    try:
        # Check magic bytes to identify format
        if len(audio_bytes) < 12:
            raise InvalidAudioFormatError("Audio data too short to identify format")
        
        # WAV format
        if audio_bytes[:4] == b'RIFF' and b'WAVE' in audio_bytes[:12]:
            return "wav"
        
        # MP3 format
        if audio_bytes[:3] == b'ID3' or (audio_bytes[0] == 0xFF and audio_bytes[1] & 0xE0 == 0xE0):
            return "mp3"
        
        # FLAC format
        if audio_bytes[:4] == b'fLaC':
            return "flac"
        
        # OGG format
        if audio_bytes[:4] == b'OggS':
            return "ogg"
        
        # Try to detect using soundfile
        try:
            with BytesIO(audio_bytes) as f:
                sf.info(f)
                return "wav"  # Default to WAV if soundfile can read it
        except:
            pass
        
        raise InvalidAudioFormatError(f"Unsupported audio format. Magic bytes: {audio_bytes[:8].hex()}")
        
    except Exception as e:
        if isinstance(e, InvalidAudioFormatError):
            raise
        logger.error(f"Audio format validation failed: {e}")
        raise InvalidAudioFormatError(f"Audio format validation failed: {e}")


def get_audio_duration(audio_bytes: bytes) -> float:
    """Get audio duration in seconds."""
    try:
        with BytesIO(audio_bytes) as f:
            info = sf.info(f)
            return info.frames / info.samplerate
            
    except Exception as e:
        logger.error(f"Failed to get audio duration: {e}")
        raise AudioProcessingError(f"Failed to get audio duration: {e}")


def convert_audio_format(
    audio_bytes: bytes,
    source_format: str,
    target_format: str
) -> bytes:
    """Convert audio between different formats."""
    try:
        # Load audio using pydub
        audio = AudioSegment.from_file(BytesIO(audio_bytes), format=source_format)
        
        # Export to target format
        output_buffer = BytesIO()
        audio.export(output_buffer, format=target_format)
        
        return output_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Audio format conversion failed: {e}")
        raise AudioProcessingError(f"Audio format conversion failed: {e}")


def validate_sample_rate(sample_rate: int) -> bool:
    """Validate sample rate is in supported range."""
    try:
        # Common sample rates
        valid_rates = [8000, 16000, 22050, 44100, 48000]
        
        if sample_rate not in valid_rates:
            # Check if it's in a reasonable range
            if not (8000 <= sample_rate <= 48000):
                raise InvalidSampleRateError(
                    f"Sample rate {sample_rate} not supported. "
                    f"Valid rates: {valid_rates} or 8000-48000 Hz"
                )
        
        return True
        
    except Exception as e:
        if isinstance(e, InvalidSampleRateError):
            raise
        logger.error(f"Sample rate validation failed: {e}")
        raise InvalidSampleRateError(f"Sample rate validation failed: {e}")
