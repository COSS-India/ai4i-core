"""
Custom exceptions for NER service.

Copied from OCR service to keep behavior consistent, but currently
kept minimal. Extend as needed.
"""


class RateLimitExceeded(Exception):
    """Raised when a client exceeds configured rate limits."""

    pass



