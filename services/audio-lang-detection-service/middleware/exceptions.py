"""
Custom exception classes for authentication and rate limiting.

Copied from language-diarization service middleware to keep behavior and structure consistent.
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


class RateLimitExceededError(HTTPException):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        self.message = message
        self.retry_after = retry_after
        super().__init__(
            status_code=429,
            detail=message,
            headers={"Retry-After": str(retry_after)},
        )


class ErrorDetail(BaseModel):
    """Error detail model for consistent error responses."""

    message: str
    code: Optional[str] = None
    timestamp: float = time.time()


class ErrorResponse(BaseModel):
    """Error response model for consistent error responses."""

    detail: ErrorDetail
    status_code: int

