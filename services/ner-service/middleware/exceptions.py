"""
Custom exception classes for authentication and rate limiting.

Copied from OCR service middleware to keep behavior and structure consistent.
"""

from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional
import time


class AuthenticationError(HTTPException):
    """Exception raised for authentication errors."""

    def __init__(self, message: str = "Not authenticated", status_code: int = 401):
        self.message = message
        super().__init__(status_code=status_code, detail=message)


class AuthorizationError(HTTPException):
    """Exception raised for authorization errors."""

    def __init__(self, message: str = "Not authorized", status_code: int = 403):
        self.message = message
        super().__init__(status_code=status_code, detail=message)


class InvalidAPIKeyError(AuthenticationError):
    """Exception raised for invalid API key."""

    def __init__(self, message: str = "Invalid API key"):
        super().__init__(message=message, status_code=401)


class ExpiredAPIKeyError(AuthenticationError):
    """Exception raised for expired API key."""

    def __init__(self, message: str = "API key has expired"):
        super().__init__(message=message, status_code=401)


class InvalidTokenError(AuthenticationError):
    """Exception raised for invalid authentication token."""

    def __init__(self, message: str = "Invalid authentication token"):
        super().__init__(message=message, status_code=401)


class ErrorDetail(BaseModel):
    """Error detail model for consistent error responses."""
    message: str
    code: Optional[str] = None
    timestamp: float = time.time()


class ErrorResponse(BaseModel):
    """Error response model for consistent error responses."""
    detail: ErrorDetail
    status_code: int


