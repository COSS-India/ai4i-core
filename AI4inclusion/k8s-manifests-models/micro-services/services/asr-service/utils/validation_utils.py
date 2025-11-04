"""
Validation utility functions for request validation.
"""

import logging
from typing import List
from models.asr_request import AudioInput

logger = logging.getLogger(__name__)

# Supported languages
SUPPORTED_LANGUAGES = [
    "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", 
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
    """Validate audio input has required content."""
    try:
        if not audio_input.audioContent and not audio_input.audioUri:
            raise InvalidAudioInputError(
                "At least one of audioContent or audioUri must be provided"
            )
        
        if audio_input.audioContent:
            # Basic base64 validation
            try:
                import base64
                base64.b64decode(audio_input.audioContent, validate=True)
            except Exception:
                raise InvalidAudioInputError("audioContent is not valid base64")
        
        if audio_input.audioUri:
            # Basic URL validation (already done by Pydantic HttpUrl)
            pass
        
        return True
        
    except Exception as e:
        if isinstance(e, InvalidAudioInputError):
            raise
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
