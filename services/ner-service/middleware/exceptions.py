"""
Custom exceptions for NER service.

Copied from OCR service to keep behavior consistent, but currently
kept minimal. Extend as needed.
"""


class RateLimitExceeded(Exception):
    """Raised when a client exceeds configured rate limits."""

    pass


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class AuthorizationError(Exception):
    """Raised when authorization/permission checks fail."""

    pass


