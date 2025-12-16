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
    def __init__(self, message: str = "Not authorized", status_code: int = 403):
        self.message = message
        super().__init__(status_code=status_code, detail=message)


class InvalidAPIKeyError(AuthenticationError):
    def __init__(self, message: str = "Invalid API key"):
        super().__init__(message=message, status_code=401)


class ExpiredAPIKeyError(AuthenticationError):
    def __init__(self, message: str = "API key has expired"):
        super().__init__(message=message, status_code=401)


class RateLimitExceededError(HTTPException):
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        self.message = message
        self.retry_after = retry_after
        super().__init__(
            status_code=429,
            detail=message,
            headers={"Retry-After": str(retry_after)},
        )


class InvalidTokenError(AuthenticationError):
    def __init__(self, message: str = "Invalid authentication token"):
        super().__init__(message=message, status_code=401)


class ErrorDetail(BaseModel):
    message: str
    code: Optional[str] = None
    timestamp: float = time.time()


class ErrorResponse(BaseModel):
    detail: ErrorDetail
    status_code: int