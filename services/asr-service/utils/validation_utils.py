"""
Validation utility functions for request validation.
"""

import logging
import base64
from typing import List
from io import BytesIO
from models.asr_request import AudioInput
from .audio_utils import validate_audio_format, get_audio_duration, AudioProcessingError, InvalidAudioFormatError
import soundfile as sf
from services.constants.error_messages import (
    NO_FILE_SELECTED,
    NO_FILE_SELECTED_MESSAGE,
    UNSUPPORTED_FORMAT,
    UNSUPPORTED_FORMAT_MESSAGE,
    FILE_TOO_LARGE,
    FILE_TOO_LARGE_MESSAGE,
    INVALID_FILE,
    INVALID_FILE_MESSAGE,
    UPLOAD_FAILED,
    UPLOAD_FAILED_MESSAGE,
    AUDIO_TOO_SHORT,
    AUDIO_TOO_SHORT_MESSAGE,
    AUDIO_TOO_LONG,
    AUDIO_TOO_LONG_MESSAGE,
    EMPTY_AUDIO_FILE,
    EMPTY_AUDIO_FILE_MESSAGE,
    UPLOAD_TIMEOUT,
    UPLOAD_TIMEOUT_MESSAGE,
)

logger = logging.getLogger(__name__)

# File validation constants
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB (for base64 encoded)
MAX_AUDIO_DURATION_SECONDS = 60  # 60 seconds maximum
MIN_AUDIO_DURATION_SECONDS = 1  # 1 second minimum
SUPPORTED_FORMATS = ["wav", "mp3"]  # Only WAV and MP3 supported

# Supported languages (Indic languages only - Triton model doesn't support English)
# Note: The Triton asr_greedy_decoder model only supports Indic languages
SUPPORTED_LANGUAGES = [
    "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", 
    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai", 
    "brx", "mni"
]


class InvalidLanguageCodeError(Exception):
    """Custom exception for invalid language code errors."""
    pass


class InvalidServiceIdError(Exception):
    """Custom exception for invalid service ID errors."""
    pass


class InvalidAudioInputError(Exception):
    """Custom exception for invalid audio input errors."""
    pass


class InvalidPreprocessorError(Exception):
    """Custom exception for invalid preprocessor errors."""
    pass


class InvalidPostprocessorError(Exception):
    """Custom exception for invalid postprocessor errors."""
    pass


class NoFileSelectedError(Exception):
    """Custom exception for no file selected errors."""
    pass


class UnsupportedFormatError(Exception):
    """Custom exception for unsupported file format errors."""
    pass


class FileTooLargeError(Exception):
    """Custom exception for file too large errors."""
    pass


class InvalidFileError(Exception):
    """Custom exception for invalid/corrupted file errors."""
    pass


class UploadFailedError(Exception):
    """Custom exception for upload failed errors."""
    pass


class AudioTooShortError(Exception):
    """Custom exception for audio too short errors."""
    pass


class AudioTooLongError(Exception):
    """Custom exception for audio too long errors."""
    pass


class EmptyAudioFileError(Exception):
    """Custom exception for empty audio file errors."""
    pass


class UploadTimeoutError(Exception):
    """Custom exception for upload timeout errors."""
    pass


def validate_language_code(language_code: str) -> bool:
    """Validate language code is supported."""
    try:
        if not language_code or len(language_code) < 2 or len(language_code) > 3:
            raise InvalidLanguageCodeError(
                f"Language code must be 2-3 characters, got: {language_code}"
            )
        
        if language_code not in SUPPORTED_LANGUAGES:
            raise InvalidLanguageCodeError(
                f"Language code '{language_code}' not supported. "
                f"Supported languages: {SUPPORTED_LANGUAGES}"
            )
        
        return True
        
    except Exception as e:
        if isinstance(e, InvalidLanguageCodeError):
            raise
        logger.error(f"Language code validation failed: {e}")
        raise InvalidLanguageCodeError(f"Language code validation failed: {e}")


def validate_service_id(service_id: str) -> bool:
    """Validate service ID format."""
    try:
        if not service_id or not isinstance(service_id, str):
            raise InvalidServiceIdError("Service ID must be a non-empty string")
        
        # Basic format validation (e.g., "ai4bharat/model-name--gpu--t4")
        if len(service_id) < 3:
            raise InvalidServiceIdError("Service ID too short")
        
        # Check for basic structure (contains at least one slash or dash)
        if '/' not in service_id and '--' not in service_id:
            logger.warning(f"Service ID '{service_id}' doesn't follow expected format")
        
        return True
        
    except Exception as e:
        if isinstance(e, InvalidServiceIdError):
            raise
        logger.error(f"Service ID validation failed: {e}")
        raise InvalidServiceIdError(f"Service ID validation failed: {e}")


def validate_audio_input(audio_input: AudioInput) -> bool:
    """Validate audio input with comprehensive file validation."""
    try:
        # Check if file is selected
        if not audio_input.audioContent and not audio_input.audioUri:
            raise NoFileSelectedError(NO_FILE_SELECTED_MESSAGE)
        
        audio_bytes = None
        
        if audio_input.audioContent:
            # Validate base64 encoding
            try:
                audio_bytes = base64.b64decode(audio_input.audioContent, validate=True)
            except Exception as e:
                logger.error(f"Base64 decode failed: {e}")
                raise InvalidFileError(INVALID_FILE_MESSAGE)
            
            # Check file size (base64 encoded size)
            encoded_size = len(audio_input.audioContent.encode('utf-8'))
            if encoded_size > MAX_FILE_SIZE_BYTES:
                raise FileTooLargeError(FILE_TOO_LARGE_MESSAGE)
            
            # Validate audio format
            try:
                audio_format = validate_audio_format(audio_bytes)
                if audio_format not in SUPPORTED_FORMATS:
                    raise UnsupportedFormatError(UNSUPPORTED_FORMAT_MESSAGE)
            except InvalidAudioFormatError:
                raise UnsupportedFormatError(UNSUPPORTED_FORMAT_MESSAGE)
            except Exception as e:
                logger.error(f"Audio format validation failed: {e}")
                raise InvalidFileError(INVALID_FILE_MESSAGE)
            
            # Check if file is empty or corrupted
            if len(audio_bytes) == 0:
                raise EmptyAudioFileError(EMPTY_AUDIO_FILE_MESSAGE)
            
            # Validate audio can be read and get duration
            try:
                duration = get_audio_duration(audio_bytes)
                
                # Check audio duration
                if duration < MIN_AUDIO_DURATION_SECONDS:
                    raise AudioTooShortError(AUDIO_TOO_SHORT_MESSAGE)
                
                if duration > MAX_AUDIO_DURATION_SECONDS:
                    raise AudioTooLongError(AUDIO_TOO_LONG_MESSAGE)
                
                # Check if audio has actual content (frames > 0)
                with BytesIO(audio_bytes) as f:
                    info = sf.info(f)
                    if info.frames == 0:
                        raise EmptyAudioFileError(EMPTY_AUDIO_FILE_MESSAGE)
                        
            except AudioProcessingError as e:
                logger.error(f"Audio processing failed: {e}")
                raise InvalidFileError(INVALID_FILE_MESSAGE)
            except (AudioTooShortError, AudioTooLongError, EmptyAudioFileError):
                raise  # Re-raise these specific errors
            except Exception as e:
                logger.error(f"Audio validation failed: {e}")
                raise InvalidFileError(INVALID_FILE_MESSAGE)
        
        if audio_input.audioUri:
            # For URI-based uploads, basic validation is done
            # Actual download and validation happens during processing
            # We can't validate file size/duration without downloading
            pass
        
        return True
        
    except (NoFileSelectedError, UnsupportedFormatError, FileTooLargeError, 
            InvalidFileError, AudioTooShortError, AudioTooLongError, 
            EmptyAudioFileError):
        # Re-raise specific file validation errors
        raise
    except Exception as e:
        logger.error(f"Audio input validation failed: {e}")
        raise InvalidAudioInputError(f"Audio input validation failed: {e}")


def validate_preprocessors(preprocessors: List[str]) -> bool:
    """Validate preprocessor names."""
    try:
        if not preprocessors:
            return True
        
        valid_preprocessors = ["vad", "denoiser"]
        
        for processor in preprocessors:
            if processor not in valid_preprocessors:
                raise InvalidPreprocessorError(
                    f"Invalid preprocessor: {processor}. "
                    f"Valid options: {valid_preprocessors}"
                )
        
        return True
        
    except Exception as e:
        if isinstance(e, InvalidPreprocessorError):
            raise
        logger.error(f"Preprocessor validation failed: {e}")
        raise InvalidPreprocessorError(f"Preprocessor validation failed: {e}")


def validate_postprocessors(postprocessors: List[str]) -> bool:
    """Validate postprocessor names."""
    try:
        if not postprocessors:
            return True
        
        valid_postprocessors = ["itn", "punctuation", "lm"]
        
        for processor in postprocessors:
            if processor not in valid_postprocessors:
                raise InvalidPostprocessorError(
                    f"Invalid postprocessor: {processor}. "
                    f"Valid options: {valid_postprocessors}"
                )
        
        return True
        
    except Exception as e:
        if isinstance(e, InvalidPostprocessorError):
            raise
        logger.error(f"Postprocessor validation failed: {e}")
        raise InvalidPostprocessorError(f"Postprocessor validation failed: {e}")
