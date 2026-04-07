"""
Validation utilities for ASR service (app-layer re-export).

Provides error classes and constants needed by the refactored app/ modules.
The canonical definitions live in utils/validation_utils.py (legacy layer);
this file re-exports the subset used inside app/ so that imports use the
standard ``app.utils.validation_utils`` path.
"""


# -- Supported languages (Indic only; English not supported by IndicASR) --
SUPPORTED_LANGUAGES = [
    "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
    "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai",
    "brx", "mni",
]


# -- Exception classes used by app/services --

class InvalidLanguageCodeError(Exception):
    """Raised when a language code is not in SUPPORTED_LANGUAGES."""
    pass


class UploadFailedError(Exception):
    """Raised when an audio file upload fails."""
    pass


class UploadTimeoutError(Exception):
    """Raised when an audio file upload times out."""
    pass


class NoFileSelectedError(Exception):
    """Raised when no audio content or URI is provided."""
    pass
